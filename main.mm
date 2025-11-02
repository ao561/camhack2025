// main.mm
// Build: clang++ -std=c++17 main.mm -framework Cocoa -framework Foundation -O2 -o WindowCreator
// Run:   ./WindowCreator ./get_blocks.py

#import <Cocoa/Cocoa.h>
#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>

@interface BlockWindow : NSWindow @end
@implementation BlockWindow @end

// Accepts "#AABBCC" or [r,g,b]
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

// Resolve absolute path
static NSString* AbsolutePath(NSString *p) {
    if ([p hasPrefix:@"/"]) return p;
    NSString *cwd = NSFileManager.defaultManager.currentDirectoryPath;
    return [cwd stringByAppendingPathComponent:p];
}

// Run python and capture stdout+stderr; returns nil on failure and sets *errOut
static NSString* RunPythonScript(NSString *absScriptPath, NSError **errOut) {
    NSTask *task = [[NSTask alloc] init];
    // Use /usr/bin/env to discover python3 on PATH (respects your .venv)
    task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/env"];
    task.arguments = @[ @"python3", absScriptPath ];

    // Optional: run with the script's directory as CWD so relative reads in the script work
    task.currentDirectoryURL = [NSURL fileURLWithPath:[absScriptPath stringByDeletingLastPathComponent]];

    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError  = pipe;

    __block NSError *launchError = nil;
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

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            fprintf(stderr, "Usage: %s <path/to/get_blocks.py>\n", argv[0]);
            return 1;
        }
        NSString *scriptPath = AbsolutePath([NSString stringWithUTF8String:argv[1]]);
        BOOL isDir = NO;
        if (![NSFileManager.defaultManager fileExistsAtPath:scriptPath isDirectory:&isDir] || isDir) {
            fprintf(stderr, "Script not found or is a directory: %s\n", scriptPath.UTF8String);
            return 1;
        }

        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];

        // Quit on Q / Esc
        [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown handler:^NSEvent* (NSEvent *e) {
            NSString *s = e.charactersIgnoringModifiers.lowercaseString;
            if ([s isEqualToString:@"q"] || e.keyCode == 53) { [NSApp terminate:nil]; return nil; }
            return e;
        }];

        // Keep and reuse windows between frames (less flicker)
        NSMutableArray<BlockWindow*> *windows = [NSMutableArray array];

        // Timer-driven updates (~5 FPS)
        __block BOOL busy = NO;
        NSTimer *timer = [NSTimer scheduledTimerWithTimeInterval:0.2 repeats:YES block:^(__unused NSTimer *t){
            if (busy) return;
            busy = YES;
            dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
                NSError *runErr = nil;
                NSString *output = RunPythonScript(scriptPath, &runErr);
                if (!output) {
                    NSLog(@"Run error: %@", runErr.localizedDescription);
                    busy = NO;
                    return;
                }

                // Find first JSON-looking line
                NSString *jsonLine = nil;
                for (NSString *line in [output componentsSeparatedByString:@"\n"]) {
                    NSString *trim = [line stringByTrimmingCharactersInSet:
                                      [NSCharacterSet whitespaceAndNewlineCharacterSet]];
                    if (trim.length && ([trim hasPrefix:@"["] || [trim hasPrefix:@"{"])) {
                        jsonLine = trim; break;
                    }
                }
                if (!jsonLine) {
                    NSLog(@"No JSON found in Python output:\n%@", output);
                    busy = NO;
                    return;
                }

                NSError *jsonErr = nil;
                NSData *jsonData = [jsonLine dataUsingEncoding:NSUTF8StringEncoding];
                id parsed = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:&jsonErr];
                if (jsonErr || ![parsed isKindOfClass:[NSArray class]]) {
                    NSLog(@"JSON parse error: %@\nLine: %@", jsonErr.localizedDescription, jsonLine);
                    busy = NO;
                    return;
                }
                NSArray *blocks = (NSArray*)parsed;

                dispatch_async(dispatch_get_main_queue(), ^{
                    // Reuse existing windows where possible
                    NSUInteger reuse = MIN(windows.count, blocks.count);
                    for (NSUInteger i=0; i<reuse; ++i) {
                        NSArray *b = blocks[i];
                        if (b.count != 5) continue;
                        CGFloat x = [b[0] doubleValue];
                        CGFloat y = [b[1] doubleValue];
                        CGFloat w = [b[2] doubleValue];
                        CGFloat h = [b[3] doubleValue];
                        NSColor *col = ColorFromJSONValue(b[4]);

                        BlockWindow *win = windows[i];
                        [win setFrame:NSMakeRect(x, y, w, h) display:NO animate:NO];
                        [win setBackgroundColor:col];
                        if (![win isVisible]) [win makeKeyAndOrderFront:nil];
                    }
                    // Add more if needed
                    for (NSUInteger i=reuse; i<blocks.count; ++i) {
                        NSArray *b = blocks[i];
                        if (b.count != 5) continue;
                        CGFloat x = [b[0] doubleValue];
                        CGFloat y = [b[1] doubleValue];
                        CGFloat w = [b[2] doubleValue];
                        CGFloat h = [b[3] doubleValue];
                        NSColor *col = ColorFromJSONValue(b[4]);

                        BlockWindow *win = [[BlockWindow alloc]
                            initWithContentRect:NSMakeRect(x, y, w, h)
                                      styleMask:NSWindowStyleMaskBorderless
                                        backing:NSBackingStoreBuffered
                                          defer:NO];
                        [win setBackgroundColor:col];
                        [win setOpaque:YES];
                        [win setLevel:NSStatusWindowLevel];   // float on top (optional)
                        [win setIgnoresMouseEvents:YES];      // let mouse pass through (optional)
                        [win orderFrontRegardless];
                        [windows addObject:win];
                    }
                    // Close extras if fewer blocks this frame
                    while (windows.count > blocks.count) {
                        BlockWindow *w = windows.lastObject;
                        [windows removeLastObject];
                        [w close];
                    }
                    busy = NO;
                });
            });
        }];
        (void)timer;

        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
}

