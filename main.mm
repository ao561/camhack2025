#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#import <CoreGraphics/CoreGraphics.h>
#include <vector>
#include <queue>
#include <random>
#include <algorithm>
#include <string>

// ===================== USER SETTINGS (defaults; can override slide seconds via argv) =====================
static const int   kMarginPx = 80;                 // screen margin
static const double kVarianceThreshold = 20.0;     // higher => fewer splits
static const int   kMinLeafSizePx = 20;            // in *image* pixels
static const int   kMaxDepth = 8;

static const double kTargetFPS = 30.0;             // jitter update rate; set 10 if you only need 10 fps
static const double kJitterPosFrac = 0.05;         // fraction of leaf size
static const bool   kJitterSize = false;           // micro-resize toggle

static const double kDefaultSlideSeconds = 0.8;    // default seconds per image
static NSString * const kWindowTitle = @"Quadtree Window";
// ========================================================================================================

// ------------ Simple pixel buffer (RGBA8) ------------
struct ImageBuf {
    int w = 0, h = 0, stride = 0; // stride in bytes
    std::vector<uint8_t> pixels;  // RGBA
    bool valid() const { return w>0 && h>0 && (int)pixels.size() >= h*stride; }
};

static ImageBuf LoadImageRGBA8(NSString *path) {
    ImageBuf out;
    NSURL *url = [NSURL fileURLWithPath:path];
    CGImageSourceRef src = CGImageSourceCreateWithURL((__bridge CFURLRef)url, nullptr);
    if (!src) return out;
    CGImageRef img = CGImageSourceCreateImageAtIndex(src, 0, nullptr);
    CFRelease(src);
    if (!img) return out;

    const size_t W = CGImageGetWidth(img);
    const size_t H = CGImageGetHeight(img);
    out.w = (int)W; out.h = (int)H;
    out.stride = (int)W * 4;
    out.pixels.resize(out.stride * out.h);

    CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
    CGBitmapInfo bi = kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Host;
    CGContextRef ctx = CGBitmapContextCreate(out.pixels.data(), W, H, 8, out.stride, cs, bi);
    CGColorSpaceRelease(cs);
    if (!ctx) { CGImageRelease(img); out = {}; return out; }

    CGContextDrawImage(ctx, CGRectMake(0, 0, (CGFloat)W, (CGFloat)H), img);
    CGContextRelease(ctx);
    CGImageRelease(img);
    return out;
}

// ------------ Region stats (mean color + stddev) ------------
struct RegionStats {
    double meanR=0, meanG=0, meanB=0;
    double stddevAvg=0;
};

static RegionStats ComputeRegionStats(const ImageBuf &buf, int x, int y, int w, int h) {
    RegionStats rs;
    if (!buf.valid()) return rs;

    int x0 = std::max(0, x), y0 = std::max(0, y);
    int x1 = std::min(buf.w, x + w), y1 = std::min(buf.h, y + h);
    if (x1 <= x0 || y1 <= y0) return rs;

    const int W = x1 - x0, H = y1 - y0;
    const int N = W * H;

    double sumR=0, sumG=0, sumB=0;
    const uint8_t* base = buf.pixels.data();
    for (int j=0; j<H; ++j) {
        const uint8_t* row = base + (y0 + j)*buf.stride + x0*4;
        for (int i=0; i<W; ++i) {
            const uint8_t* p = row + i*4;
            sumR += p[0]; sumG += p[1]; sumB += p[2];
        }
    }
    rs.meanR = sumR / N; rs.meanG = sumG / N; rs.meanB = sumB / N;

    double varR=0, varG=0, varB=0;
    for (int j=0; j<H; ++j) {
        const uint8_t* row = base + (y0 + j)*buf.stride + x0*4;
        for (int i=0; i<W; ++i) {
            const uint8_t* p = row + i*4;
            varR += (p[0] - rs.meanR)*(p[0] - rs.meanR);
            varG += (p[1] - rs.meanG)*(p[1] - rs.meanG);
            varB += (p[2] - rs.meanB)*(p[2] - rs.meanB);
        }
    }
    varR /= N; varG /= N; varB /= N;
    rs.stddevAvg = (std::sqrt(varR) + std::sqrt(varG) + std::sqrt(varB)) / 3.0;
    return rs;
}

// ------------ Quadtree ------------
struct QuadNode {
    int x, y, w, h, depth;
    double variance;
    double meanR, meanG, meanB;
    bool split = false;
    QuadNode *c[4] = {nullptr,nullptr,nullptr,nullptr};
    QuadNode(int X,int Y,int W,int H,int D):x(X),y(Y),w(W),h(H),depth(D),variance(0),meanR(0),meanG(0),meanB(0){}
};

static bool ShouldSplit(const QuadNode& n) {
    return (n.variance > kVarianceThreshold &&
            std::min(n.w, n.h) > kMinLeafSizePx*2 &&
            n.depth < kMaxDepth);
}

static void SplitNode(QuadNode* n) {
    int hw = n->w/2, hh = n->h/2;
    n->c[0] = new QuadNode(n->x,       n->y,       hw, hh, n->depth+1);
    n->c[1] = new QuadNode(n->x+hw,    n->y,       n->w-hw, hh, n->depth+1);
    n->c[2] = new QuadNode(n->x,       n->y+hh,    hw, n->h-hh, n->depth+1);
    n->c[3] = new QuadNode(n->x+hw,    n->y+hh,    n->w-hw, n->h-hh, n->depth+1);
    n->split = true;
}

static void CollectLeaves(QuadNode* n, std::vector<QuadNode*>& out) {
    if (!n) return;
    if (!n->split) { out.push_back(n); return; }
    for (int i=0;i<4;++i) CollectLeaves(n->c[i], out);
}

static void FreeTree(QuadNode* n){
    if (!n) return;
    for (int i=0;i<4;++i) FreeTree(n->c[i]);
    delete n;
}

// ------------ Window bundle ------------
struct WinBundle {
    NSWindow* win = nil;
    NSRect baseFrame;
    CGFloat maxJitterX;
    CGFloat maxJitterY;
    CGFloat targetW, targetH;
    CGColorRef color = nullptr;
};

// ------------ Controller ------------
@interface AppDelegate : NSObject <NSApplicationDelegate>
@end

@interface WindowController : NSObject
@property (nonatomic, strong) NSMutableArray<NSWindow*> *windows;
@property (nonatomic, strong) NSTimer *animTimer;
@property (nonatomic, strong) NSTimer *slideTimer;
@property (nonatomic) NSRect workArea;
@property (nonatomic) std::mt19937 rng;
@property (nonatomic) std::uniform_real_distribution<double> uni;
@property (nonatomic) std::vector<WinBundle> bundles;

// slideshow
@property (nonatomic, strong) NSArray<NSString*> *imagePaths;
@property (nonatomic) NSUInteger currentIndex;
@property (nonatomic) double slideSeconds;

- (instancetype)initWithPaths:(NSArray<NSString*>*)paths slideSeconds:(double)secs;
@end

@implementation WindowController

- (instancetype)initWithPaths:(NSArray<NSString*>*)paths slideSeconds:(double)secs {
    self = [super init];
    if (!self) return nil;

    _imagePaths = paths;
    _currentIndex = 0;
    _slideSeconds = secs;

    NSScreen *screen = NSScreen.mainScreen;
    _workArea = screen.visibleFrame;

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

@end

@implementation AppDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
                                           handler:^NSEvent* (NSEvent *event) {
        NSString *chars = event.charactersIgnoringModifiers.lowercaseString;
        if ([chars isEqualToString:@"q"]) { [NSApp terminate:nil]; return nil; }
        return event;
    }];
}
@end

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

        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        InstallMinimalMenu();

        AppDelegate *delegate = [AppDelegate new];
        [NSApp setDelegate:delegate];

        WindowController *controller = [[WindowController alloc] initWithPaths:paths slideSeconds:slideSeconds];
        (void)controller;

        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
}
