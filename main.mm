// main.mm
// Build: clang++ -std=c++17 main.mm -framework Cocoa -framework Foundation -O2 -o WindowCreator
// Run:   ./WindowCreator ./get_blocks.py                      (single frame default from script)
//        ./WindowCreator ./get_blocks.py --mode all           (multiple frames)
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

// Run python once and capture stdout+stderr; returns nil on failure and sets *errOut
static NSString* RunPythonOnce(NSString *absScriptPath,
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

    // Prefer arrays (your script prints arrays), else try object
    NSRange firstBracket = [trim rangeOfString:@"["];
    if (firstBracket.location != NSNotFound) {
        NSRange lastBracket = [trim rangeOfString:@"]" options:NSBackwardsSearch];
        if (lastBracket.location != NSNotFound && lastBracket.location >= firstBracket.location) {
            NSRange jsonRange = NSMakeRange(firstBracket.location,
                                            lastBracket.location - firstBracket.location + 1);
            return [trim substringWithRange:jsonRange];
        }
    }
    // Fallback: try object
    NSRange firstBrace = [trim rangeOfString:@"{"];
    if (firstBrace.location != NSNotFound) {
        NSRange lastBrace = [trim rangeOfString:@"}" options:NSBackwardsSearch];
        if (lastBrace.location != NSNotFound && lastBrace.location >= firstBrace.location) {
            NSRange jsonRange = NSMakeRange(firstBrace.location,
                                            lastBrace.location - firstBrace.location + 1);
            return [trim substringWithRange:jsonRange];
        }
    }
    return nil;
}

// Is this array a single frame (array of blocks)?
static BOOL LooksLikeBlocksArray(NSArray *arr) {
    if (![arr isKindOfClass:[NSArray class]]) return NO;
    if (arr.count == 0) return YES; // empty blocks still a single frame
    id first = arr[0];
    if (![first isKindOfClass:[NSArray class]]) return NO;
    NSArray *maybeBlock = (NSArray*)first;
    if (maybeBlock.count < 4) return NO;
    // first 4 entries numeric: x,y,w,h
    return [maybeBlock[0] isKindOfClass:[NSNumber class]] &&
           [maybeBlock[1] isKindOfClass:[NSNumber class]] &&
           [maybeBlock[2] isKindOfClass:[NSNumber class]] &&
           [maybeBlock[3] isKindOfClass:[NSNumber class]];
}

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

        // Forward any extra args (e.g. --mode all --target 1024x768)
        NSMutableArray<NSString*> *scriptArgs = [NSMutableArray array];
        for (int i = 2; i < argc; ++i) {
            [scriptArgs addObject:[NSString stringWithUTF8String:argv[i]]];
        }

        // 1) Run Python once and cache frames
        NSError *runErr = nil;
        NSString *output = RunPythonOnce(scriptPath, scriptArgs, &runErr);
        if (!output) {
            fprintf(stderr, "Failed to run Python: %s\n",
                    runErr.localizedDescription.UTF8String);
            return 1;
        }

        NSString *jsonStr = ExtractJSONNSString(output);
        if (!jsonStr) {
            fprintf(stderr, "No JSON found in Python output.\n");
            return 1;
        }

        NSError *jsonErr = nil;
        NSData *jsonData = [jsonStr dataUsingEncoding:NSUTF8StringEncoding];
        id parsed = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:&jsonErr];
        if (jsonErr || ![parsed isKindOfClass:[NSArray class]]) {
            fprintf(stderr, "JSON parse error: %s\n", jsonErr.localizedDescription.UTF8String);
            return 1;
        }

        NSArray *top = (NSArray*)parsed;
        NSArray<NSArray*> *frames = nil;
        if (LooksLikeBlocksArray(top)) {
            // SINGLE frame → wrap as one frame
            frames = @[ top ];
        } else {
            // MULTI frame → ensure each element is a blocks array (or empty)
            NSMutableArray<NSArray*> *norm = [NSMutableArray arrayWithCapacity:top.count];
            for (id item in top) {
                if ([item isKindOfClass:[NSArray class]] && LooksLikeBlocksArray((NSArray*)item)) {
                    [norm addObject:(NSArray*)item];
                } else if ([item isKindOfClass:[NSArray class]] && [(NSArray*)item count] == 0) {
                    [norm addObject:(NSArray*)item];
                } else {
                    // Skip malformed frames instead of failing hard
                    continue;
                }
            }
            frames = norm;
        }
        if (frames.count == 0) {
            fprintf(stderr, "No frames to display.\n");
            return 1;
        }

        // 2) App + animation over cached frames
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

        // ~10 FPS (0.1s) over cached frames
        [NSTimer scheduledTimerWithTimeInterval:0.1 repeats:YES block:^(__unused NSTimer *t) {
            NSArray *blocks = frames[frameIndex % frames.count];
            frameIndex++;

            // Reuse existing windows
            NSUInteger reuse = MIN(windows.count, blocks.count);
            for (NSUInteger i=0; i<reuse; ++i) {
                NSArray *b = blocks[i];
                if ([b count] < 4) continue;
                CGFloat x = [b[0] doubleValue];
                CGFloat y = [b[1] doubleValue];
                CGFloat w = [b[2] doubleValue];
                CGFloat h = [b[3] doubleValue];
                NSColor *col = ([b count] >= 5) ? ColorFromJSONValue(b[4]) : [NSColor blackColor];

                BlockWindow *win = windows[i];
                [win setFrame:NSMakeRect(x, y, w, h) display:NO animate:NO];
                [win setBackgroundColor:col];
                if (![win isVisible]) [win makeKeyAndOrderFront:nil];
            }
            // Create missing windows
            for (NSUInteger i=reuse; i<blocks.count; ++i) {
                NSArray *b = blocks[i];
                if ([b count] < 4) continue;
                CGFloat x = [b[0] doubleValue];
                CGFloat y = [b[1] doubleValue];
                CGFloat w = [b[2] doubleValue];
                CGFloat h = [b[3] doubleValue];
                NSColor *col = ([b count] >= 5) ? ColorFromJSONValue(b[4]) : [NSColor blackColor];

                BlockWindow *win = [[BlockWindow alloc]
                    initWithContentRect:NSMakeRect(x, y, w, h)
                              styleMask:NSWindowStyleMaskBorderless
                                backing:NSBackingStoreBuffered
                                  defer:NO];
                [win setBackgroundColor:col];
                [win setOpaque:YES];
                [win setLevel:NSStatusWindowLevel];
                [win setIgnoresMouseEvents:YES];
                [win orderFrontRegardless];
                [windows addObject:win];
            }
            // Close extras
            while (windows.count > blocks.count) {
                BlockWindow *w = windows.lastObject;
                [windows removeLastObject];
                [w close];
            }
        }];

        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
}
