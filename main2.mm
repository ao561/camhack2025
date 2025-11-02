// clang++ -std=c++17 main2.mm -framework Cocoa -o WindowCreator
// ./WindowCreator ./blocks.json

#import <Cocoa/Cocoa.h>
#import <Foundation/Foundation.h>
#import <sys/event.h>
#import <sys/stat.h>
#import <math.h>

// Adjustable: fraction of area that must be covered by new blocks
static const double OVERLAP_THRESHOLD = 0.7;

@interface BlockWindow : NSWindow
@property NSRect frameRect;
@end
@implementation BlockWindow
@end

static CGFloat overlapArea(NSRect a, NSRect b) {
    CGFloat xOverlap = fmax(0, fmin(NSMaxX(a), NSMaxX(b)) - fmax(NSMinX(a), NSMinX(b)));
    CGFloat yOverlap = fmax(0, fmin(NSMaxY(a), NSMaxY(b)) - fmax(NSMinY(a), NSMinY(b)));
    return xOverlap * yOverlap;
}

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

static NSArray* readBlocksFromJSON(NSString *jsonPath) {
    for (int i = 0; i < 3; i++) { // retry a few times if file temporarily unavailable
        NSData *data = [NSData dataWithContentsOfFile:jsonPath];
        if (data) {
            NSError *err = nil;
            NSArray *blocks = [NSJSONSerialization JSONObjectWithData:data options:0 error:&err];
            if (!err && [blocks isKindOfClass:[NSArray class]]) return blocks;
        }
        [NSThread sleepForTimeInterval:0.02];
    }
    return nil;
}

// Create a lightweight “fake titlebar” window (borderless but styled)
static BlockWindow* createBlockWindow(NSRect rect, NSColor *bodyColor, NSString *title) {
    BlockWindow *win = [[BlockWindow alloc] initWithContentRect:rect
                                                       styleMask:NSWindowStyleMaskBorderless
                                                         backing:NSBackingStoreBuffered
                                                           defer:NO];
    win.frameRect = rect;
    [win setOpaque:NO];
    [win setBackgroundColor:[NSColor clearColor]];
    [win setReleasedWhenClosed:NO];
    [win setHasShadow:YES];
    [win setLevel:NSFloatingWindowLevel];
    [win setMovableByWindowBackground:YES];

    NSView *contentView = [win contentView];
    [contentView setWantsLayer:YES];
    contentView.layer.backgroundColor = [NSColor clearColor].CGColor;
    contentView.layer.cornerRadius = 6.0;
    contentView.layer.masksToBounds = YES;

    // Create header bar (for appearance only)
    CGFloat headerHeight = 22.0;
    NSView *header = [[NSView alloc] initWithFrame:NSMakeRect(0, rect.size.height - headerHeight, rect.size.width, headerHeight)];
    [header setWantsLayer:YES];
    header.layer.backgroundColor = [NSColor colorWithWhite:0.85 alpha:1.0].CGColor;

    // Optional: small text label in header
    if (title && title.length > 0) {
        NSTextField *label = [[NSTextField alloc] initWithFrame:NSMakeRect(8, 3, rect.size.width - 16, headerHeight - 6)];
        [label setStringValue:title];
        [label setEditable:NO];
        [label setBordered:NO];
        [label setBackgroundColor:[NSColor clearColor]];
        [label setTextColor:[NSColor darkGrayColor]];
        [label setFont:[NSFont systemFontOfSize:12 weight:NSFontWeightMedium]];
        [header addSubview:label];
    }

    // Body region
    NSView *body = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, rect.size.width, rect.size.height - headerHeight)];
    [body setWantsLayer:YES];
    body.layer.backgroundColor = bodyColor.CGColor;

    [contentView addSubview:body];
    [contentView addSubview:header];

    [win makeKeyAndOrderFront:nil];
    return win;
}

// Update windows with new blocks, removing old ones that are mostly covered
static void updateWindows(NSString *jsonPath, NSMutableArray<BlockWindow *> *windows) {
    NSArray *blocks = readBlocksFromJSON(jsonPath);
    if (!blocks || blocks.count == 0) return;

    dispatch_async(dispatch_get_main_queue(), ^{
        NSMutableArray<BlockWindow *> *newWindows = [NSMutableArray array];
        NSMutableArray<NSValue *> *newRects = [NSMutableArray array];

        for (NSDictionary *block in blocks) {
            NSNumber *x = block[@"x"];
            NSNumber *y = block[@"y"];
            NSNumber *w = block[@"w"];
            NSNumber *h = block[@"h"];
            id colorVal = block[@"color"];
            if (!x || !y || !w || !h || !colorVal) continue;

            NSRect rect = NSMakeRect([x doubleValue], [y doubleValue], [w doubleValue], [h doubleValue]);
            NSColor *color = colorFromValue(colorVal);
            NSString *title = block[@"title"] ?: @"";

            BlockWindow *win = createBlockWindow(rect, color, title);
            [newWindows addObject:win];
            [newRects addObject:[NSValue valueWithRect:rect]];
        }

        // Remove old windows mostly covered by new ones
        NSMutableArray<BlockWindow *> *remaining = [NSMutableArray array];
        for (BlockWindow *oldWin in windows) {
            NSRect oldRect = oldWin.frameRect;
            CGFloat totalOverlap = 0;
            for (NSValue *v in newRects) {
                NSRect newRect = [v rectValue];
                totalOverlap += overlapArea(oldRect, newRect);
            }
            CGFloat overlapRatio = totalOverlap / (oldRect.size.width * oldRect.size.height);
            if (overlapRatio < OVERLAP_THRESHOLD) {
                [remaining addObject:oldWin];
            } else {
                [oldWin close];
            }
        }

        [windows removeAllObjects];
        [windows addObjectsFromArray:remaining];
        [windows addObjectsFromArray:newWindows];
    });
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            NSLog(@"Usage: WindowCreator <path/to/blocks.json>");
            return 1;
        }

        NSString *jsonPath = [NSString stringWithUTF8String:argv[1]];
        NSMutableArray<BlockWindow *> *windows = [NSMutableArray array];

        [NSApplication sharedApplication];
        updateWindows(jsonPath, windows);

        // File watcher
        int fd = open([jsonPath fileSystemRepresentation], O_EVTONLY);
        if (fd < 0) {
            NSLog(@"Error: Cannot open file for watching: %@", jsonPath);
        } else {
            dispatch_queue_t queue = dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0);
            dispatch_source_t source = dispatch_source_create(DISPATCH_SOURCE_TYPE_VNODE, fd,
                DISPATCH_VNODE_WRITE | DISPATCH_VNODE_DELETE | DISPATCH_VNODE_RENAME, queue);

            dispatch_source_set_event_handler(source, ^{
                unsigned long flags = dispatch_source_get_data(source);
                if (flags & (DISPATCH_VNODE_DELETE | DISPATCH_VNODE_RENAME)) {
                    dispatch_source_cancel(source);
                    close(fd);
                    int newFd = open([jsonPath fileSystemRepresentation], O_EVTONLY);
                    if (newFd >= 0) {
                        dispatch_source_t newSource = dispatch_source_create(DISPATCH_SOURCE_TYPE_VNODE, newFd,
                            DISPATCH_VNODE_WRITE | DISPATCH_VNODE_DELETE | DISPATCH_VNODE_RENAME, queue);
                        dispatch_source_set_event_handler(newSource, ^{
                            updateWindows(jsonPath, windows);
                        });
                        dispatch_resume(newSource);
                    }
                } else if (flags & DISPATCH_VNODE_WRITE) {
                    updateWindows(jsonPath, windows);
                }
            });

            dispatch_source_set_cancel_handler(source, ^{
                close(fd);
            });
            dispatch_resume(source);
        }

        [NSApp run];
    }
    return 0;
}
