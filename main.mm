#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#include <random>

/*
clang++ -std=c++17 -fobjc-arc -isysroot $(xcrun --show-sdk-path) -framework Cocoa -O2 -o window_stress main.mm
*/

static const int kWindowCount = 100;
static const double kTargetFPS = 60.0;
static const CGFloat kMinSize = 80.0;
static const CGFloat kMaxSize = 220.0;
static const CGFloat kJitterPos = 8.0;
static const CGFloat kJitterSize = 40.0;

@interface WindowController : NSObject
@property (nonatomic, strong) NSMutableArray<NSWindow*> *windows;
@property (nonatomic, strong) NSTimer *timer;
@property (nonatomic) NSRect workArea;
@property (nonatomic) std::mt19937 rng;
@property (nonatomic) std::uniform_real_distribution<double> uni;
@end

@implementation WindowController

- (instancetype)init {
    self = [super init];
    if (!self) return nil;
    _windows = [NSMutableArray arrayWithCapacity:kWindowCount];
    _rng.seed((uint32_t)CFAbsoluteTimeGetCurrent());
    _uni = std::uniform_real_distribution<double>(0.0, 1.0);

    NSScreen *screen = NSScreen.mainScreen;
    _workArea = screen.visibleFrame;

    // Create normal titled windows
    for (int i = 0; i < kWindowCount; ++i) {
        CGFloat w = kMinSize + (kMaxSize - kMinSize) * _uni(_rng);
        CGFloat h = kMinSize + (kMaxSize - kMinSize) * _uni(_rng);
        CGFloat x = _workArea.origin.x + _uni(_rng) * MAX(1.0, _workArea.size.width  - w);
        CGFloat y = _workArea.origin.y + _uni(_rng) * MAX(1.0, _workArea.size.height - h);

        NSRect rect = NSMakeRect(x, y, w, h);

        NSWindow *win = [[NSWindow alloc]
            initWithContentRect:rect
                      styleMask:(NSWindowStyleMaskTitled |
                                 NSWindowStyleMaskClosable |
                                 NSWindowStyleMaskMiniaturizable |
                                 NSWindowStyleMaskResizable)
                        backing:NSBackingStoreBuffered
                          defer:NO];

        win.title = [NSString stringWithFormat:@"Window %d", i + 1];
        win.opaque = YES;
        win.hasShadow = YES;
        win.level = NSNormalWindowLevel;

        NSView *content = win.contentView;
        content.wantsLayer = YES;
        CGFloat r = _uni(_rng), g = _uni(_rng), b = _uni(_rng);
        content.layer.backgroundColor = CGColorCreateGenericRGB(r, g, b, 1.0);

        [win orderFrontRegardless];
        [_windows addObject:win];
    }

    // Animation timer
    _timer = [NSTimer scheduledTimerWithTimeInterval:1.0 / kTargetFPS
                                              target:self
                                            selector:@selector(tick:)
                                            userInfo:nil
                                             repeats:YES];
    return self;
}

- (void)tick:(NSTimer *)__unused t {
    for (NSWindow *win in _windows) {
        NSRect f = win.frame;

        CGFloat dx = ((CGFloat)_uni(_rng) * 2.0 - 1.0) * kJitterPos;
        CGFloat dy = ((CGFloat)_uni(_rng) * 2.0 - 1.0) * kJitterPos;
        CGFloat dw = ((CGFloat)_uni(_rng) * 2.0 - 1.0) * kJitterSize;
        CGFloat dh = ((CGFloat)_uni(_rng) * 2.0 - 1.0) * kJitterSize;

        CGFloat newW = fmax(kMinSize, fmin(kMaxSize, f.size.width  + dw));
        CGFloat newH = fmax(kMinSize, fmin(kMaxSize, f.size.height + dh));

        CGFloat newX = f.origin.x + dx;
        CGFloat newY = f.origin.y + dy;

        newX = fmin(fmax(_workArea.origin.x, newX),
                    _workArea.origin.x + _workArea.size.width  - newW);
        newY = fmin(fmax(_workArea.origin.y, newY),
                    _workArea.origin.y + _workArea.size.height - newH);

        NSRect newF = NSMakeRect(newX, newY, newW, newH);
        [win setFrame:newF display:NO animate:NO];
    }
}

@end

// ----------------------------------------------------
// App delegate to handle keyboard input ("Q" to quit)
// ----------------------------------------------------
@interface AppDelegate : NSObject <NSApplicationDelegate>
@end

@implementation AppDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    // Install a global event monitor for key presses
    [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
                                           handler:^NSEvent* (NSEvent *event) {
        NSString *chars = event.charactersIgnoringModifiers.lowercaseString;
        if ([chars isEqualToString:@"q"]) {
            [NSApp terminate:nil];
            return nil; // swallow event
        }
        return event; // pass other keys through
    }];
}
@end

// Minimal menu bar so the app shows properly in Dock
static void InstallMinimalMenu() {
    NSMenu *menubar = [NSMenu new];
    NSMenuItem *appMenuItem = [NSMenuItem new];
    [menubar addItem:appMenuItem];
    [NSApp setMainMenu:menubar];

    NSMenu *appMenu = [NSMenu new];
    NSString *quitTitle = [NSString stringWithFormat:@"Quit %@", NSRunningApplication.currentApplication.localizedName];
    NSMenuItem *quit = [[NSMenuItem alloc] initWithTitle:quitTitle
                                                  action:@selector(terminate:)
                                           keyEquivalent:@"q"];
    [appMenu addItem:quit];
    [appMenuItem setSubmenu:appMenu];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        InstallMinimalMenu();

        AppDelegate *delegate = [AppDelegate new];
        [NSApp setDelegate:delegate];

        WindowController *controller = [WindowController new];
        (void)controller;

        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
}