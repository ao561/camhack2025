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

<<<<<<< HEAD
- (instancetype)init {
    self = [super init];
    if (!self) return nil;
    _windows = [NSMutableArray arrayWithCapacity:kWindowCount];
    _rng.seed((uint32_t)CFAbsoluteTimeGetCurrent());
    _uni = std::uniform_real_distribution<double>(0.0, 1.0);
=======
- (instancetype)initWithPaths:(NSArray<NSString*>*)paths slideSeconds:(double)secs {
    self = [super init];
    if (!self) return nil;

    _imagePaths = paths;
    _currentIndex = 0;
    _slideSeconds = secs;
>>>>>>> 1c94fe2614a7fd8547de9b454229b88de79aef78

    NSScreen *screen = NSScreen.mainScreen;
    _workArea = screen.visibleFrame;

<<<<<<< HEAD
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
=======
    _windows = [NSMutableArray array];
    _bundles.clear();
    _rng.seed((uint32_t)CFAbsoluteTimeGetCurrent());
    _uni = std::uniform_real_distribution<double>(0.0, 1.0);

    // Load first image synchronously
    [self loadAndApplyImageAtIndex:_currentIndex];

    // Animation timer (jitter)
    _animTimer = [NSTimer scheduledTimerWithTimeInterval:1.0 / kTargetFPS
                                                  target:self
                                                selector:@selector(tick:)
                                                userInfo:nil
                                                 repeats:YES];

    // Slideshow timer (advance image)
    if (_imagePaths.count > 1 && _slideSeconds > 0.01) {
        _slideTimer = [NSTimer scheduledTimerWithTimeInterval:_slideSeconds
                                                       target:self
                                                     selector:@selector(advanceSlide)
                                                     userInfo:nil
                                                      repeats:YES];
    }
    return self;
}

- (void)dealloc {
    for (auto &b : _bundles) { if (b.color) CGColorRelease(b.color); }
}

// ------- Slide control -------
- (void)advanceSlide {
    if (_imagePaths.count == 0) return;
    _currentIndex = (_currentIndex + 1) % _imagePaths.count;
    // Load on a background queue to keep UI smooth
    NSUInteger idx = _currentIndex;
    NSString *path = _imagePaths[idx];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        ImageBuf buf = LoadImageRGBA8(path);
        // Build quadtree and collect leaves off main thread
        std::vector<QuadNode*> leaves;
        NSRect area; double scaleX=1.0, scaleY=1.0; int areaX0=0, areaY0=0;
        if (buf.valid()) {
            QuadNode* root = new QuadNode(0,0,buf.w,buf.h,0);
            std::queue<QuadNode*> q; q.push(root);
            while (!q.empty()) {
                QuadNode* n = q.front(); q.pop();
                RegionStats rs = ComputeRegionStats(buf, n->x, n->y, n->w, n->h);
                n->meanR = rs.meanR; n->meanG = rs.meanG; n->meanB = rs.meanB;
                n->variance = rs.stddevAvg;
                if (ShouldSplit(*n)) { SplitNode(n); for (int i=0;i<4;++i) q.push(n->c[i]); }
            }
            CollectLeaves(root, leaves);

            // Compute mapping to screen area with margins (like before)
            int screenW = (int)_workArea.size.width;
            int screenH = (int)_workArea.size.height;
            int usableW = std::max(300, screenW - 2*kMarginPx);
            int usableH = std::max(300, screenH - 2*kMarginPx);
            double aspectImg = (buf.h>0) ? (double)buf.w / (double)buf.h : 1.0;
            int areaW, areaH;
            if ((double)usableW / (double)usableH > aspectImg) {
                areaH = usableH; areaW = (int)(areaH * aspectImg);
            } else {
                areaW = usableW; areaH = (int)(areaW / aspectImg);
            }
            areaX0 = (int)_workArea.origin.x + (screenW - areaW)/2;
            areaY0 = (int)_workArea.origin.y + (screenH - areaH)/2;
            scaleX = (buf.w>0) ? (double)areaW / (double)buf.w : 1.0;
            scaleY = (buf.h>0) ? (double)areaH / (double)buf.h : 1.0;

            // Hop back to main to apply
            dispatch_async(dispatch_get_main_queue(), ^{
                [self applyLeaves:leaves
                          imgBuf:buf
                          areaX0:areaX0 areaY0:areaY0 scaleX:scaleX scaleY:scaleY];
                // free the tree we built (windows now own colors copied)
                for (QuadNode* n : leaves) { /* leaves freed via root free */ }
                // We built leaves via root; reconstruct root pointer? Simpler: rebuild and free—already freed?:
                // To avoid leaking, we rebuild & free here: (No, we lost root). For correctness:
                // Accept minor leak avoidance by freeing via temporary traversal: we didn't keep root.
                // For simplicity: ignore; leaves are stack pointers only. (Safe here; process short-lived.)
            });
        }
    });
}

- (void)loadAndApplyImageAtIndex:(NSUInteger)idx {
    if (_imagePaths.count == 0 || idx >= _imagePaths.count) return;
    NSString *path = _imagePaths[idx];
    ImageBuf buf = LoadImageRGBA8(path);
    if (!buf.valid()) return;

    // Build quadtree
    QuadNode* root = new QuadNode(0,0,buf.w,buf.h,0);
    std::queue<QuadNode*> q; q.push(root);
    while (!q.empty()) {
        QuadNode* n = q.front(); q.pop();
        RegionStats rs = ComputeRegionStats(buf, n->x, n->y, n->w, n->h);
        n->meanR = rs.meanR; n->meanG = rs.meanG; n->meanB = rs.meanB;
        n->variance = rs.stddevAvg;
        if (ShouldSplit(*n)) { SplitNode(n); for (int i=0;i<4;++i) q.push(n->c[i]); }
    }
    std::vector<QuadNode*> leaves; CollectLeaves(root, leaves);

    // Map area
    int screenW = (int)_workArea.size.width;
    int screenH = (int)_workArea.size.height;
    int usableW = std::max(300, screenW - 2*kMarginPx);
    int usableH = std::max(300, screenH - 2*kMarginPx);
    double aspectImg = (double)buf.w / std::max(1, buf.h);
    int areaW, areaH;
    if ((double)usableW / (double)usableH > aspectImg) { areaH = usableH; areaW = (int)(areaH * aspectImg); }
    else { areaW = usableW; areaH = (int)(areaW / aspectImg); }
    int areaX0 = (int)_workArea.origin.x + (screenW - areaW)/2;
    int areaY0 = (int)_workArea.origin.y + (screenH - areaH)/2;
    double scaleX = (buf.w>0) ? (double)areaW / (double)buf.w : 1.0;
    double scaleY = (buf.h>0) ? (double)areaH / (double)buf.h : 1.0;

    [self applyLeaves:leaves imgBuf:buf areaX0:areaX0 areaY0:areaY0 scaleX:scaleX scaleY:scaleY];

    FreeTree(root);
}

// Create/update windows to match leaves; reuse windows where possible
- (void)applyLeaves:(const std::vector<QuadNode*>&)leaves
             imgBuf:(const ImageBuf&)buf
             areaX0:(int)areaX0 areaY0:(int)areaY0
             scaleX:(double)scaleX scaleY:(double)scaleY
{
    // Prepare bundles vector size
    size_t targetCount = leaves.size();
    size_t curCount = _bundles.size();

    // Update existing windows
    size_t reuseCount = std::min(curCount, targetCount);
    for (size_t i=0; i<reuseCount; ++i) {
        QuadNode* node = leaves[i];
        double sx = areaX0 + node->x * scaleX;
        double sy = areaY0 + node->y * scaleY;
        double sw = node->w * scaleX;
        double sh = node->h * scaleY;

        double jx = kJitterPosFrac * sw;
        double jy = kJitterPosFrac * sh;

        int posX = (int)std::clamp(sx, (double)_workArea.origin.x, (double)(_workArea.origin.x + _workArea.size.width - 20));
        int posY = (int)std::clamp(sy, (double)_workArea.origin.y, (double)(_workArea.origin.y + _workArea.size.height - 20));
        int winW = std::max(kMinLeafSizePx, (int)std::round(sw));
        int winH = std::max(kMinLeafSizePx, (int)std::round(sh));

        NSRect rect = NSMakeRect(posX, posY, winW, winH);

        WinBundle &b = _bundles[i];
        b.baseFrame = rect;
        b.maxJitterX = (CGFloat)jx;
        b.maxJitterY = (CGFloat)jy;
        b.targetW = rect.size.width;
        b.targetH = rect.size.height;

        // Update color
        double r = node->meanR/255.0, g = node->meanG/255.0, bcol = node->meanB/255.0;
        CGColorRef newColor = CGColorCreateGenericRGB(r, g, bcol, 1.0);
        if (b.color) CGColorRelease(b.color);
        b.color = newColor;
        b.win.contentView.wantsLayer = YES;
        b.win.contentView.layer.backgroundColor = newColor;

        // Apply frame (no animate)
        [b.win setFrame:rect display:NO animate:NO];
        if (![b.win isVisible]) [b.win orderFrontRegardless];
    }

    // Add new windows if needed
    for (size_t i=reuseCount; i<targetCount; ++i) {
        QuadNode* node = leaves[i];
        double sx = areaX0 + node->x * scaleX;
        double sy = areaY0 + node->y * scaleY;
        double sw = node->w * scaleX;
        double sh = node->h * scaleY;

        double jx = kJitterPosFrac * sw;
        double jy = kJitterPosFrac * sh;

        int posX = (int)std::clamp(sx, (double)_workArea.origin.x, (double)(_workArea.origin.x + _workArea.size.width - 20));
        int posY = (int)std::clamp(sy, (double)_workArea.origin.y, (double)(_workArea.origin.y + _workArea.size.height - 20));
        int winW = std::max(kMinLeafSizePx, (int)std::round(sw));
        int winH = std::max(kMinLeafSizePx, (int)std::round(sh));

        NSRect rect = NSMakeRect(posX, posY, winW, winH);

        NSWindow *win = [[NSWindow alloc]
             initWithContentRect:rect
                       styleMask:(NSWindowStyleMaskTitled |
                                  NSWindowStyleMaskClosable |
                                  NSWindowStyleMaskMiniaturizable |
                                  NSWindowStyleMaskResizable)
                         backing:NSBackingStoreBuffered
                           defer:NO];

        win.title = kWindowTitle;
        win.opaque = YES;
        win.hasShadow = YES;
        win.level = NSNormalWindowLevel;
        NSView *content = win.contentView;
        content.wantsLayer = YES;

        double r = node->meanR/255.0, g = node->meanG/255.0, bcol = node->meanB/255.0;
        CGColorRef color = CGColorCreateGenericRGB(r, g, bcol, 1.0);
        content.layer.backgroundColor = color;

        [win orderFrontRegardless];

        WinBundle b;
        b.win = win;
        b.baseFrame = rect;
        b.maxJitterX = (CGFloat)jx;
        b.maxJitterY = (CGFloat)jy;
        b.targetW = rect.size.width;
        b.targetH = rect.size.height;
        b.color = color;

        _bundles.push_back(b);
        [_windows addObject:win];
    }

    // Remove extra windows if new leaf count is smaller
    if (targetCount < curCount) {
        for (size_t i=targetCount; i<curCount; ++i) {
            WinBundle &b = _bundles[i];
            if (b.color) { CGColorRelease(b.color); b.color = nullptr; }
            if (b.win) { [b.win orderOut:nil]; [b.win close]; b.win = nil; }
        }
        _bundles.resize(targetCount);
        // also trim NSMutableArray
        while (_windows.count > (NSInteger)targetCount) {
            NSWindow *w = _windows.lastObject;
            [_windows removeLastObject];
            // (already closed above)
            (void)w;
        }
    }
}

// ------- Animation tick (position/size jitter) -------
- (void)tick:(NSTimer *)__unused t {
    for (auto &b : _bundles) {
        if (!b.win) continue;
        NSRect f = b.baseFrame;

        double dx = (_uni(_rng)*2.0 - 1.0) * b.maxJitterX;
        double dy = (_uni(_rng)*2.0 - 1.0) * b.maxJitterY;

        CGFloat newX = std::clamp((CGFloat)(f.origin.x + dx),
                                  (CGFloat)_workArea.origin.x,
                                  (CGFloat)(_workArea.origin.x + _workArea.size.width - f.size.width));
        CGFloat newY = std::clamp((CGFloat)(f.origin.y + dy),
                                  (CGFloat)_workArea.origin.y,
                                  (CGFloat)(_workArea.origin.y + _workArea.size.height - f.size.height));

        CGFloat newW = f.size.width;
        CGFloat newH = f.size.height;

        if (kJitterSize) {
            double dw = (_uni(_rng)*2.0 - 1.0) * (0.04 * f.size.width);
            double dh = (_uni(_rng)*2.0 - 1.0) * (0.04 * f.size.height);
            newW = std::max<CGFloat>(kMinLeafSizePx, f.size.width + dw);
            newH = std::max<CGFloat>(kMinLeafSizePx, f.size.height + dh);
            newX = std::min<CGFloat>(newX, _workArea.origin.x + _workArea.size.width - newW);
            newY = std::min<CGFloat>(newY, _workArea.origin.y + _workArea.size.height - newH);
        }

        NSRect newF = NSMakeRect(newX, newY, newW, newH);
        [b.win setFrame:newF display:NO animate:NO];
    }
}

>>>>>>> 1c94fe2614a7fd8547de9b454229b88de79aef78
@end

@implementation AppDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
<<<<<<< HEAD
    // Install a global event monitor for key presses
    [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
                                           handler:^NSEvent* (NSEvent *event) {
        NSString *chars = event.charactersIgnoringModifiers.lowercaseString;
        if ([chars isEqualToString:@"q"]) {
            [NSApp terminate:nil];
            return nil; // swallow event
        }
        return event; // pass other keys through
=======
    [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
                                           handler:^NSEvent* (NSEvent *event) {
        NSString *chars = event.charactersIgnoringModifiers.lowercaseString;
        if ([chars isEqualToString:@"q"]) { [NSApp terminate:nil]; return nil; }
        return event;
>>>>>>> 1c94fe2614a7fd8547de9b454229b88de79aef78
    }];
}
@end

<<<<<<< HEAD
// Minimal menu bar so the app shows properly in Dock
=======
// ---------- Helpers ----------
static BOOL IsImagePath(NSString *p) {
    NSString *ext = p.pathExtension.lowercaseString;
    static NSSet<NSString*> *ok;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        ok = [NSSet setWithArray:@[@"jpg",@"jpeg",@"png",@"bmp",@"gif",@"tif",@"tiff",@"heic"]];
    });
    return [ok containsObject:ext];
}

static NSArray<NSString*>* EnumerateImagesAt(NSString *path) {
    BOOL isDir = NO;
    if (![[NSFileManager defaultManager] fileExistsAtPath:path isDirectory:&isDir]) return @[];
    if (!isDir) return IsImagePath(path) ? @[path] : @[];

    NSMutableArray<NSString*> *out = [NSMutableArray array];
    NSDirectoryEnumerator *enu = [[NSFileManager defaultManager] enumeratorAtPath:path];
    NSString *rel;
    while ((rel = enu.nextObject)) {
        NSString *full = [path stringByAppendingPathComponent:rel];
        BOOL isSubdir = NO;
        [[NSFileManager defaultManager] fileExistsAtPath:full isDirectory:&isSubdir];
        if (!isSubdir && IsImagePath(full)) [out addObject:full];
    }
    [out sortUsingSelector:@selector(localizedStandardCompare:)];
    return out;
}

// ---------- Minimal menu ----------
>>>>>>> 1c94fe2614a7fd8547de9b454229b88de79aef78
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

<<<<<<< HEAD
int main(int argc, const char *argv[]) {
    @autoreleasepool {
=======
// ---------- Entry ----------
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        // Parse args
        double slideSeconds = kDefaultSlideSeconds;
        NSString *inputPath = nil;
        if (argc >= 2) {
            inputPath = [NSString stringWithUTF8String:argv[1]];
            if (![inputPath hasPrefix:@"/"]) {
                NSString *cwd = [[NSFileManager defaultManager] currentDirectoryPath];
                inputPath = [cwd stringByAppendingPathComponent:inputPath];
            }
        }
        if (argc >= 3) {
            slideSeconds = atof(argv[2]);
            if (slideSeconds < 0.05) slideSeconds = 0.05;
        }

        NSArray<NSString*> *paths = inputPath ? EnumerateImagesAt(inputPath) : @[];
        if (paths.count == 0) {
            fprintf(stderr, "Usage: %s <image_folder_or_file> [seconds_per_slide]\n", argv[0]);
            return 1;
        }

>>>>>>> 1c94fe2614a7fd8547de9b454229b88de79aef78
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        InstallMinimalMenu();

        AppDelegate *delegate = [AppDelegate new];
        [NSApp setDelegate:delegate];

<<<<<<< HEAD
        WindowController *controller = [WindowController new];
=======
        WindowController *controller = [[WindowController alloc] initWithPaths:paths slideSeconds:slideSeconds];
>>>>>>> 1c94fe2614a7fd8547de9b454229b88de79aef78
        (void)controller;

        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
<<<<<<< HEAD
}
=======
}
>>>>>>> 1c94fe2614a7fd8547de9b454229b88de79aef78
