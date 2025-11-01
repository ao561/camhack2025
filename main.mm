//clang++ -std=c++17 main.mm -framework Cocoa -o WindowCreator
//./WindowCreator ./get_blocks.py

// main.mm
#import <Cocoa/Cocoa.h>
#import <Foundation/Foundation.h>
#import <thread>
#import <chrono>

@interface BlockWindow : NSWindow
@end
@implementation BlockWindow
@end

// Handles both ["#AABBCC"] and [r,g,b]
static NSColor* colorFromValue(id colVal) {
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

// Run Python script and capture stdout as NSString
static NSString* runPythonScript(NSString *scriptPath) {
    NSTask *task = [[NSTask alloc] init];
    task.launchPath = @"/usr/local/bin/python3.12";
    task.arguments = @[scriptPath];
    
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    
    NSFileHandle *handle = [pipe fileHandleForReading];
    [task launch];
    NSData *data = [handle readDataToEndOfFile];
    [task waitUntilExit];
    
    NSString *output = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    return output;
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            NSLog(@"Error: Please provide the path to get_blocks.py");
            return 1;
        }
        NSString *scriptPath = [NSString stringWithUTF8String:argv[1]];
        NSMutableArray<BlockWindow *> *windows = [NSMutableArray array];

        [NSApplication sharedApplication];

        dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
            while (true) {
                @autoreleasepool {
                    NSString *output = runPythonScript(scriptPath);
                    if (!output || output.length == 0) {
                        NSLog(@"Python script produced no output");
                        continue;
                    }

                    // Find JSON-looking line
                    NSString *jsonLine = nil;
                    NSArray *lines = [output componentsSeparatedByString:@"\n"];
                    for (NSString *line in lines) {
                        if ([line hasPrefix:@"["] || [line hasPrefix:@"{"]) {
                            jsonLine = line;
                            break;
                        }
                    }
                    if (!jsonLine) {
                        NSLog(@"No JSON found in Python output:\n%@", output);
                        continue;
                    }

                    NSError *err = nil;
                    NSData *jsonData = [jsonLine dataUsingEncoding:NSUTF8StringEncoding];
                    NSArray *blocks = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:&err];
                    if (err) {
                        NSLog(@"Failed to parse JSON: %@", err);
                        continue;
                    }

                    dispatch_async(dispatch_get_main_queue(), ^{
                        for (NSWindow *w in windows) [w close];
                        [windows removeAllObjects];

                        for (NSArray *block in blocks) {
                            if ([block count] == 5) {
                                CGFloat x = [block[0] doubleValue];
                                CGFloat y = [block[1] doubleValue];
                                CGFloat w = [block[2] doubleValue];
                                CGFloat h = [block[3] doubleValue];
                                NSColor *color = colorFromValue(block[4]);

                                BlockWindow *win = [[BlockWindow alloc] initWithContentRect:NSMakeRect(x, y, w, h)
                                                                                   styleMask:NSWindowStyleMaskBorderless
                                                                                     backing:NSBackingStoreBuffered
                                                                                       defer:NO];
                                [win setBackgroundColor:color];
                                [win setLevel:NSStatusWindowLevel];
                                [win makeKeyAndOrderFront:nil];
                                [windows addObject:win];
                            }
                        }
                    });
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(200)); // ~5 FPS
            }
        });

        [NSApp run];
    }
    return 0;
}
