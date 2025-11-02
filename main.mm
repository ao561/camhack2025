// main.mm
// Build: clang++ -std=c++17 main.mm -framework Cocoa -framework Foundation -O2 -o WindowCreator
// Run:   ./WindowCreator ./get_blocks.py                      (single frame default -> regenerates continuously)
//        ./WindowCreator ./get_blocks.py --mode single        (same as above)
//        ./WindowCreator ./get_blocks.py --mode all           (multiple frames cached & looped)
//        ./WindowCreator ./get_blocks.py --mode all --target 1024x768

#import <Cocoa/Cocoa.h>
#import <Foundation/Foundation.h>

@interface BlockWindow : NSWindow @end
@implementation BlockWindow @end

static NSColor* ColorFromJSONValue(id colVal) {
    if ([colVal isKindOfClass:[NSArray class]] && [colVal count] == 3) {
        CGFloat r = [colVal[0] doubleValue] / 255.0;
        CGFloat g = [colVal[1] doubleValue] / 255.0;
        CGFloat b = [colVal[2] doubleValue] / 255.0;
        return [NSColor colorWithRed:r green:g blue:b alpha:1.0];
    } else if ([colVal isKindOfClass:[NSString class]] && [colVal hasPrefix:@"#"]) {
        unsigned rgbValue = 0;
        NSScanner *scanner = [NSScanner scannerWithString:colVal];
        [scanner setScanLocation:1];
        [scanner scanHexInt:&rgbValue];
        CGFloat r = ((rgbValue >> 16) & 0xFF) / 255.0;
        CGFloat g = ((rgbValue >> 8) & 0xFF) / 255.0;
        CGFloat b = (rgbValue & 0xFF) / 255.0;
        return [NSColor colorWithRed:r green:g blue:b alpha:1.0];
    }
    return [NSColor blackColor];
}

static NSString* AbsolutePath(NSString *p) {
    if ([p hasPrefix:@"/"]) return p;
    return [NSFileManager.defaultManager.currentDirectoryPath stringByAppendingPathComponent:p];
}

// ---------- Python runner ----------
static NSString* RunPython(NSString *absScriptPath,
                           NSArray<NSString*> *extraArgs,
                           NSError **errOut) {
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/env"];
    NSMutableArray *args = [NSMutableArray arrayWithObject:@"python3"];
    [args addObject:absScriptPath];
    if (extraArgs.count) [args addObjectsFromArray:extraArgs];
    task.arguments = args;
    task.currentDirectoryURL = [NSURL fileURLWithPath:[absScriptPath stringByDeletingLastPathComponent]];
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError  = pipe;
    NSError *launchError = nil;
    if (![task launchAndReturnError:&launchError]) {
        if (errOut) *errOut = launchError;
        return nil;
    }
    NSData *data = [[pipe fileHandleForReading] readDataToEndOfFile];
    [task waitUntilExit];
    NSString *out = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    if (task.terminationStatus != 0) {
        if (errOut) {
            NSString *msg = [NSString stringWithFormat:@"Python exit code %d. Output:\n%@",
                             task.terminationStatus, out ?: @"<no output>"];
            *errOut = [NSError errorWithDomain:@"Runner" code:task.terminationStatus
                                      userInfo:@{NSLocalizedDescriptionKey: msg}];
        }
        return nil;
    }
    return out ?: @"";
}

// Robustly slice JSON out of any surrounding logs (multi-line safe)
static NSString* ExtractJSONNSString(NSString *output) {
    if (!output) return nil;
    NSString *trim = [output stringByTrimmingCharactersInSet:
                      [NSCharacterSet whitespaceAndNewlineCharacterSet]];
    NSRange fb = [trim rangeOfString:@"["];
    if (fb.location != NSNotFound) {
        NSRange lb = [trim rangeOfString:@"]" options:NSBackwardsSearch];
        if (lb.location != NSNotFound && lb.location >= fb.location) {
            return [trim substringWithRange:
                    NSMakeRange(fb.location, lb.location - fb.location + 1)];
        }
    }
    NSRange fc = [trim rangeOfString:@"{"];
    if (fc.location != NSNotFound) {
        NSRange lc = [trim rangeOfString:@"}" options:NSBackwardsSearch];
        if (lc.location != NSNotFound && lc.location >= fc.location) {
            return [trim substringWithRange:
                    NSMakeRange(fc.location, lc.location - fc.location + 1)];
        }
    }
    return nil;
}

// Is this array a single frame (array of blocks)?
static BOOL LooksLikeBlocksArray(NSArray *arr) {
    if (![arr isKindOfClass:[NSArray class]]) return NO;
    if (arr.count == 0) return YES;
    id first = arr[0];
    if (![first isKindOfClass:[NSArray class]]) return NO;
    NSArray *maybeBlock = (NSArray*)first;
    if (maybeBlock.count < 4) return NO;
    return [maybeBlock[0] isKindOfClass:[NSNumber class]] &&
           [maybeBlock[1] isKindOfClass:[NSNumber class]] &&
           [maybeBlock[2] isKindOfClass:[NSNumber class]] &&
           [maybeBlock[3] isKindOfClass:[NSNumber class]];
}

// ---------- App ----------
int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            fprintf(stderr, "Usage: %s <path/to/get_blocks.py> [script args...]\n", argv[0]);
            return 1;
        }
        NSString *scriptPath = AbsolutePath([NSString stringWithUTF8String:argv[1]]);
        BOOL isDir = NO;
        if (![NSFileManager.defaultManager fileExistsAtPath:scriptPath isDirectory:&isDir] || isDir) {
            fprintf(stderr, "Script not found or is a directory: %s\n", scriptPath.UTF8String);
            return 1;
        }

        // Gather args for Python (e.g., --mode single / --mode all ...)
        NSMutableArray<NSString*> *scriptArgs = [NSMutableArray array];
        for (int i = 2; i < argc; ++i) {
            [scriptArgs addObject:[NSString stringWithUTF8String:argv[i]]];
        }

        // First run to detect mode and (maybe) cache frames
        NSError *runErr = nil;
        NSString *output = RunPython(scriptPath, scriptArgs, &runErr);
        if (!output) {
            fprintf(stderr, "Failed to run Python: %s\n",
                    runErr.localizedDescription.UTF8String);
            return 1;
        }
        NSString *jsonStr = ExtractJSONNSString(output);
        if (!jsonStr) { fprintf(stderr, "No JSON found in Python output.\n"); return 1; }

        NSError *jsonErr = nil;
        NSData *jsonData = [jsonStr dataUsingEncoding:NSUTF8StringEncoding];
        id parsed = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:&jsonErr];
        if (jsonErr || ![parsed isKindOfClass:[NSArray class]]) {
            fprintf(stderr, "JSON parse error: %s\n", jsonErr.localizedDescription.UTF8String);
            return 1;
        }

        NSArray *top = (NSArray*)parsed;
        BOOL singleMode = LooksLikeBlocksArray(top);
        NSArray<NSArray*> *cachedFrames = nil;
        if (singleMode) {
            // single frame now — but we'll *stream* new frames by re-running Python each tick
            cachedFrames = @[ top ]; // seed display immediately
        } else {
            // multi-frame — cache and loop them
            NSMutableArray<NSArray*> *norm = [NSMutableArray arrayWithCapacity:top.count];
            for (id item in top) if ([item isKindOfClass:[NSArray class]]) [norm addObject:(NSArray*)item];
            cachedFrames = norm;
            if (cachedFrames.count == 0) { fprintf(stderr, "No frames to display.\n"); return 1; }
        }

        // Setup app
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
                                              handler:^NSEvent* (NSEvent *e) {
            NSString *s = e.charactersIgnoringModifiers.lowercaseString;
            if ([s isEqualToString:@"q"] || e.keyCode == 53) { [NSApp terminate:nil]; return nil; }
            return e;
        }];

        NSMutableArray<BlockWindow*> *windows = [NSMutableArray array];
        __block NSUInteger frameIndex = 0;
        __block BOOL busy = NO;

        // Timer (~10 FPS)
        [NSTimer scheduledTimerWithTimeInterval:0.1 repeats:YES block:^(__unused NSTimer *t) {
            if (busy) return;
            busy = YES;

            // Frame source:
            if (singleMode) {
                // Re-run Python each tick to regenerate blocks for the single image
                dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
                    NSError *err2 = nil;
                    NSString *out2 = RunPython(scriptPath, scriptArgs, &err2);
                    if (!out2) { busy = NO; return; }
                    NSString *json2 = ExtractJSONNSString(out2);
                    if (!json2) { busy = NO; return; }

                    NSError *jerr2 = nil;
                    NSData *jd2 = [json2 dataUsingEncoding:NSUTF8StringEncoding];
                    id p2 = [NSJSONSerialization JSONObjectWithData:jd2 options:0 error:&jerr2];
                    if (jerr2 || ![p2 isKindOfClass:[NSArray class]]) { busy = NO; return; }

                    NSArray *top2 = (NSArray*)p2;
                    NSArray *blocks = LooksLikeBlocksArray(top2) ? top2 : (top2.count ? top2[0] : @[]);
                    dispatch_async(dispatch_get_main_queue(), ^{
                        // draw blocks
                        NSUInteger reuse = MIN(windows.count, blocks.count);
                        for (NSUInteger i=0; i<reuse; ++i) {
                            NSArray *b = blocks[i];
                            if (b.count < 4) continue;
                            CGFloat x = [b[0] doubleValue];
                            CGFloat y = [b[1] doubleValue];
                            CGFloat w = [b[2] doubleValue];
                            CGFloat h = [b[3] doubleValue];
                            NSColor *col = (b.count >= 5) ? ColorFromJSONValue(b[4]) : [NSColor blackColor];
                            BlockWindow *win = windows[i];
                            [win setFrame:NSMakeRect(x, y, w, h) display:NO animate:NO];
                            [win setBackgroundColor:col];
                            if (![win isVisible]) [win makeKeyAndOrderFront:nil];
                        }
                        for (NSUInteger i=reuse; i<blocks.count; ++i) {
                            NSArray *b = blocks[i];
                            if (b.count < 4) continue;
                            CGFloat x = [b[0] doubleValue];
                            CGFloat y = [b[1] doubleValue];
                            CGFloat w = [b[2] doubleValue];
                            CGFloat h = [b[3] doubleValue];
                            NSColor *col = (b.count >= 5) ? ColorFromJSONValue(b[4]) : [NSColor blackColor];
                            BlockWindow *win = [[BlockWindow alloc]
                                initWithContentRect:NSMakeRect(x, y, w, h)
                                          styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable)
                                            backing:NSBackingStoreBuffered
                                              defer:NO];
                            [win setTitle:@"Block Window"];
                            [win setBackgroundColor:col];
                            [win setOpaque:YES];
                            [win setLevel:NSStatusWindowLevel];
                            [win setIgnoresMouseEvents:YES];
                            [win orderFrontRegardless];
                            [windows addObject:win];
                        }
                        while (windows.count > blocks.count) {
                            BlockWindow *w = windows.lastObject;
                            [windows removeLastObject];
                            [w close];
                        }
                        busy = NO;
                    });
                });
            } else {
                // Use cached multi-frames
                NSArray *blocks = cachedFrames[frameIndex % cachedFrames.count];
                frameIndex++;

                // draw blocks
                NSUInteger reuse = MIN(windows.count, blocks.count);
                for (NSUInteger i=0; i<reuse; ++i) {
                    NSArray *b = blocks[i];
                    if (b.count < 4) continue;
                    CGFloat x = [b[0] doubleValue];
                    CGFloat y = [b[1] doubleValue];
                    CGFloat w = [b[2] doubleValue];
                    CGFloat h = [b[3] doubleValue];
                    NSColor *col = (b.count >= 5) ? ColorFromJSONValue(b[4]) : [NSColor blackColor];
                    BlockWindow *win = windows[i];
                    [win setFrame:NSMakeRect(x, y, w, h) display:NO animate:NO];
                    [win setBackgroundColor:col];
                    if (![win isVisible]) [win makeKeyAndOrderFront:nil];
                }
                for (NSUInteger i=reuse; i<blocks.count; ++i) {
                    NSArray *b = blocks[i];
                    if (b.count < 4) continue;
                    CGFloat x = [b[0] doubleValue];
                    CGFloat y = [b[1] doubleValue];
                    CGFloat w = [b[2] doubleValue];
                    CGFloat h = [b[3] doubleValue];
                    NSColor *col = (b.count >= 5) ? ColorFromJSONValue(b[4]) : [NSColor blackColor];
                    BlockWindow *win = [[BlockWindow alloc]
                        initWithContentRect:NSMakeRect(x, y, w, h)
                                  styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable)
                                    backing:NSBackingStoreBuffered
                                      defer:NO];
                    [win setTitle:@"Block Window"];
                    [win setBackgroundColor:col];
                    [win setOpaque:YES];
                    [win setLevel:NSStatusWindowLevel];
                    [win setIgnoresMouseEvents:YES];
                    [win orderFrontRegardless];
                    [windows addObject:win];
                }
                while (windows.count > blocks.count) {
                    BlockWindow *w = windows.lastObject;
                    [windows removeLastObject];
                    [w close];
                }
                busy = NO;
            }
        }];

        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
}
