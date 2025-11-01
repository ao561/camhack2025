// quadtree_video.mm
// Video/animation version with frame-by-frame quadtree window updates
// Compile: clang++ -std=c++17 -fobjc-arc -framework Cocoa -O2 -o quadtree_video quadtree_video.mm
// Run: ./quadtree_video frame1.jpg frame2.jpg frame3.jpg ...

#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#include <vector>
#include <memory>
#include <random>
#include <cmath>
#include <string>

// -------- SETTINGS --------
static const int VARIANCE_THRESHOLD = 20;
static const int MIN_WINDOW_SIZE = 20;
static const int MAX_DEPTH = 8;
static const CGFloat JITTER_POS = 0.05;
static const CGFloat MARGIN = 80.0;
static const double FRAME_DURATION = 1.0; // seconds per frame

// -------- Helper Functions --------
struct RGB {
    uint8_t r, g, b;
    RGB(uint8_t _r = 0, uint8_t _g = 0, uint8_t _b = 0) : r(_r), g(_g), b(_b) {}
};

RGB calculateAvgColor(NSBitmapImageRep *bitmap, int x, int y, int w, int h) {
    int x0 = std::max(0, x);
    int y0 = std::max(0, y);
    int x1 = std::min((int)[bitmap pixelsWide], x + w);
    int y1 = std::min((int)[bitmap pixelsHigh], y + h);
    
    if (x1 <= x0 || y1 <= y0) return RGB(0, 0, 0);
    
    unsigned char *data = [bitmap bitmapData];
    int bpr = (int)[bitmap bytesPerRow];
    int bpp = (int)[bitmap bitsPerPixel] / 8;
    
    long long sumR = 0, sumG = 0, sumB = 0;
    int count = 0;
    
    for (int py = y0; py < y1; ++py) {
        for (int px = x0; px < x1; ++px) {
            unsigned char *pixel = data + py * bpr + px * bpp;
            sumR += pixel[0];
            sumG += pixel[1];
            sumB += pixel[2];
            count++;
        }
    }
    
    if (count == 0) return RGB(0, 0, 0);
    return RGB(sumR / count, sumG / count, sumB / count);
}

double calculateVariance(NSBitmapImageRep *bitmap, int x, int y, int w, int h) {
    int x0 = std::max(0, x);
    int y0 = std::max(0, y);
    int x1 = std::min((int)[bitmap pixelsWide], x + w);
    int y1 = std::min((int)[bitmap pixelsHigh], y + h);
    
    if (x1 <= x0 || y1 <= y0) return 0.0;
    
    unsigned char *data = [bitmap bitmapData];
    int bpr = (int)[bitmap bytesPerRow];
    int bpp = (int)[bitmap bitsPerPixel] / 8;
    
    long long sumR = 0, sumG = 0, sumB = 0;
    int count = 0;
    
    for (int py = y0; py < y1; ++py) {
        for (int px = x0; px < x1; ++px) {
            unsigned char *pixel = data + py * bpr + px * bpp;
            sumR += pixel[0];
            sumG += pixel[1];
            sumB += pixel[2];
            count++;
        }
    }
    
    if (count == 0) return 0.0;
    
    double meanR = (double)sumR / count;
    double meanG = (double)sumG / count;
    double meanB = (double)sumB / count;
    
    double varR = 0, varG = 0, varB = 0;
    for (int py = y0; py < y1; ++py) {
        for (int px = x0; px < x1; ++px) {
            unsigned char *pixel = data + py * bpr + px * bpp;
            varR += (pixel[0] - meanR) * (pixel[0] - meanR);
            varG += (pixel[1] - meanG) * (pixel[1] - meanG);
            varB += (pixel[2] - meanB) * (pixel[2] - meanB);
        }
    }
    
    double stdR = std::sqrt(varR / count);
    double stdG = std::sqrt(varG / count);
    double stdB = std::sqrt(varB / count);
    
    return (stdR + stdG + stdB) / 3.0;
}

// -------- QuadNode Class --------
class QuadNode {
public:
    int x, y, w, h;
    int depth;
    RGB color;
    double variance;
    std::vector<std::unique_ptr<QuadNode>> children;
    
    QuadNode(int _x, int _y, int _w, int _h, NSBitmapImageRep *bitmap, int _depth = 0)
        : x(_x), y(_y), w(_w), h(_h), depth(_depth) {
        color = calculateAvgColor(bitmap, x, y, w, h);
        variance = calculateVariance(bitmap, x, y, w, h);
    }
    
    bool shouldSplit() const {
        return variance > VARIANCE_THRESHOLD &&
               std::min(w, h) > MIN_WINDOW_SIZE * 2 &&
               depth < MAX_DEPTH;
    }
    
    void split(NSBitmapImageRep *bitmap) {
        int hw = w / 2;
        int hh = h / 2;
        
        children.push_back(std::make_unique<QuadNode>(x,      y,      hw, hh, bitmap, depth + 1));
        children.push_back(std::make_unique<QuadNode>(x + hw, y,      hw, hh, bitmap, depth + 1));
        children.push_back(std::make_unique<QuadNode>(x,      y + hh, hw, hh, bitmap, depth + 1));
        children.push_back(std::make_unique<QuadNode>(x + hw, y + hh, hw, hh, bitmap, depth + 1));
    }
    
    void getLeafNodes(std::vector<QuadNode*> &leaves) {
        if (children.empty()) {
            leaves.push_back(this);
        } else {
            for (auto &child : children) {
                child->getLeafNodes(leaves);
            }
        }
    }
};

std::unique_ptr<QuadNode> buildQuadtree(NSBitmapImageRep *bitmap) {
    int imgW = (int)[bitmap pixelsWide];
    int imgH = (int)[bitmap pixelsHigh];
    
    auto root = std::make_unique<QuadNode>(0, 0, imgW, imgH, bitmap);
    std::vector<QuadNode*> queue = {root.get()};
    
    while (!queue.empty()) {
        QuadNode *node = queue.front();
        queue.erase(queue.begin());
        
        if (node->shouldSplit()) {
            node->split(bitmap);
            for (auto &child : node->children) {
                queue.push_back(child.get());
            }
        }
    }
    
    return root;
}

// -------- Video Controller --------
@interface QuadtreeVideoController : NSObject
@property (nonatomic, strong) NSMutableArray<NSWindow*> *windows;
@property (nonatomic, strong) NSMutableArray<NSString*> *framePaths;
@property (nonatomic, strong) NSTimer *frameTimer;
@property (nonatomic) NSInteger currentFrame;
@property (nonatomic) std::mt19937 rng;
@property (nonatomic) std::uniform_real_distribution<double> uni;
@property (nonatomic) CGFloat areaX0, areaY0, scaleX, scaleY;
@property (nonatomic) std::vector<std::pair<int, int>> windowRegions; // (x, y, w, h) for each window
- (instancetype)initWithFramePaths:(NSArray<NSString*> *)paths;
- (void)updateFrame;
@end

@implementation QuadtreeVideoController

- (instancetype)initWithFramePaths:(NSArray<NSString*> *)paths {
    self = [super init];
    if (!self) return nil;
    
    _framePaths = [NSMutableArray arrayWithArray:paths];
    _windows = [NSMutableArray array];
    _currentFrame = 0;
    _rng.seed((uint32_t)CFAbsoluteTimeGetCurrent());
    _uni = std::uniform_real_distribution<double>(0.0, 1.0);
    
    // Load first frame to build initial quadtree structure
    NSString *firstPath = _framePaths[0];
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:firstPath];
    if (!image) {
        NSLog(@"Failed to load first frame: %@", firstPath);
        return nil;
    }
    
    NSBitmapImageRep *bitmap = nil;
    for (NSImageRep *rep in [image representations]) {
        if ([rep isKindOfClass:[NSBitmapImageRep class]]) {
            bitmap = (NSBitmapImageRep *)rep;
            break;
        }
    }
    
    if (!bitmap) {
        NSSize size = [image size];
        [image lockFocus];
        bitmap = [[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(0, 0, size.width, size.height)];
        [image unlockFocus];
    }
    
    NSLog(@"Building quadtree for frame structure...");
    auto root = buildQuadtree(bitmap);
    
    std::vector<QuadNode*> leaves;
    root->getLeafNodes(leaves);
    NSLog(@"Leaf count: %lu", leaves.size());
    
    // Screen setup
    NSScreen *screen = [NSScreen mainScreen];
    NSRect screenFrame = [screen visibleFrame];
    CGFloat screenW = screenFrame.size.width;
    CGFloat screenH = screenFrame.size.height;
    
    CGFloat usableW = std::max(300.0, screenW - 2 * MARGIN);
    CGFloat usableH = std::max(300.0, screenH - 2 * MARGIN);
    
    CGFloat imgW = [bitmap pixelsWide];
    CGFloat imgH = [bitmap pixelsHigh];
    CGFloat aspect = imgW / imgH;
    
    CGFloat areaW, areaH;
    if (usableW / usableH > aspect) {
        areaH = usableH;
        areaW = areaH * aspect;
    } else {
        areaW = usableW;
        areaH = areaW / aspect;
    }
    
    _areaX0 = screenFrame.origin.x + (screenW - areaW) / 2;
    _areaY0 = screenFrame.origin.y + (screenH - areaH) / 2;
    _scaleX = areaW / imgW;
    _scaleY = areaH / imgH;
    
    // Create windows and store their regions
    for (QuadNode *node : leaves) {
        CGFloat screenX = _areaX0 + node->x * _scaleX;
        CGFloat screenY = _areaY0 + node->y * _scaleY;
        CGFloat screenWNode = node->w * _scaleX;
        CGFloat screenHNode = node->h * _scaleY;
        
        // Add jitter
        CGFloat jx = (_uni(_rng) * 2.0 - 1.0) * JITTER_POS * screenWNode;
        CGFloat jy = (_uni(_rng) * 2.0 - 1.0) * JITTER_POS * screenHNode;
        
        CGFloat posX = std::max(0.0, std::min(screenX + jx, screenW - screenWNode));
        CGFloat posY = std::max(0.0, std::min(screenY + jy, screenH - screenHNode));
        CGFloat winW = std::max((CGFloat)MIN_WINDOW_SIZE, screenWNode);
        CGFloat winH = std::max((CGFloat)MIN_WINDOW_SIZE, screenHNode);
        
        NSRect rect = NSMakeRect(posX, posY, winW, winH);
        
        NSWindow *win = [[NSWindow alloc]
            initWithContentRect:rect
                      styleMask:(NSWindowStyleMaskTitled |
                                NSWindowStyleMaskClosable |
                                NSWindowStyleMaskMiniaturizable)
                        backing:NSBackingStoreBuffered
                          defer:NO];
        
        win.title = @"Program Window";
        win.opaque = YES;
        win.hasShadow = YES;
        win.level = NSNormalWindowLevel;
        
        NSView *content = win.contentView;
        content.wantsLayer = YES;
        CGFloat r = node->color.r / 255.0;
        CGFloat g = node->color.g / 255.0;
        CGFloat b = node->color.b / 255.0;
        content.layer.backgroundColor = CGColorCreateGenericRGB(r, g, b, 1.0);
        
        [win orderFront:nil];
        [_windows addObject:win];
        
        // Store region info for updates
        _windowRegions.push_back({node->x, node->y, node->w, node->h});
    }
    
    NSLog(@"Created %lu windows for %lu frames", (unsigned long)_windows.count, (unsigned long)_framePaths.count);
    NSLog(@"Playing at %.1f seconds per frame", FRAME_DURATION);
    
    // Start frame timer
    _frameTimer = [NSTimer scheduledTimerWithTimeInterval:FRAME_DURATION
                                                    target:self
                                                  selector:@selector(updateFrame)
                                                  userInfo:nil
                                                   repeats:YES];
    
    return self;
}

- (void)updateFrame {
    _currentFrame = (_currentFrame + 1) % _framePaths.count;
    
    NSLog(@"Displaying frame %ld/%lu", (long)_currentFrame + 1, (unsigned long)_framePaths.count);
    
    NSString *framePath = _framePaths[_currentFrame];
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:framePath];
    if (!image) {
        NSLog(@"Failed to load frame: %@", framePath);
        return;
    }
    
    NSBitmapImageRep *bitmap = nil;
    for (NSImageRep *rep in [image representations]) {
        if ([rep isKindOfClass:[NSBitmapImageRep class]]) {
            bitmap = (NSBitmapImageRep *)rep;
            break;
        }
    }
    
    if (!bitmap) {
        NSSize size = [image size];
        [image lockFocus];
        bitmap = [[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(0, 0, size.width, size.height)];
        [image unlockFocus];
    }
    
    // Update each window's color based on its region in the new frame
    for (NSUInteger i = 0; i < _windows.count; ++i) {
        auto region = _windowRegions[i];
        RGB color = calculateAvgColor(bitmap, region.first, region.second, 
                                     _windowRegions[i].first, _windowRegions[i].second);
        
        CGFloat r = color.r / 255.0;
        CGFloat g = color.g / 255.0;
        CGFloat b = color.b / 255.0;
        
        NSWindow *win = _windows[i];
        win.contentView.layer.backgroundColor = CGColorCreateGenericRGB(r, g, b, 1.0);
    }
}

- (void)closeAllWindows {
    [_frameTimer invalidate];
    for (NSWindow *win in _windows) {
        [win close];
    }
    [NSApp terminate:nil];
}

@end

// -------- App Delegate --------
@interface AppDelegate : NSObject <NSApplicationDelegate>
@property (nonatomic, strong) QuadtreeVideoController *controller;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [NSEvent addLocalMonitorForEventsMatchingMask:NSEventMaskKeyDown
                                           handler:^NSEvent* (NSEvent *event) {
        if (event.keyCode == 53) { // Escape key
            [self.controller closeAllWindows];
            return nil;
        }
        return event;
    }];
}

@end

// -------- Main --------
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            fprintf(stderr, "Usage: %s <frame1.jpg> <frame2.jpg> ...\n", argv[0]);
            fprintf(stderr, "Provide multiple image files to play as video frames\n");
            return 1;
        }
        
        NSMutableArray<NSString*> *framePaths = [NSMutableArray array];
        for (int i = 1; i < argc; ++i) {
            NSString *path = [NSString stringWithUTF8String:argv[i]];
            [framePaths addObject:path];
        }
        
        NSLog(@"Loading %lu frames...", (unsigned long)framePaths.count);
        
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        
        AppDelegate *delegate = [AppDelegate new];
        [NSApp setDelegate:delegate];
        
        delegate.controller = [[QuadtreeVideoController alloc] initWithFramePaths:framePaths];
        if (!delegate.controller) {
            return 1;
        }
        
        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
}
