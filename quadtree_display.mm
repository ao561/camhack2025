// quadtree_display.mm
// Port of quadtree_display_pywin.py to Objective-C++
// Compile: clang++ -std=c++17 -fobjc-arc -framework Cocoa -O2 -o quadtree_display quadtree_display.mm
// Run: ./quadtree_display image.jpg

#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#include <vector>
#include <memory>
#include <random>
#include <cmath>

// -------- SETTINGS --------
static const int VARIANCE_THRESHOLD = 20;
static const int MIN_WINDOW_SIZE = 20;
static const int MAX_DEPTH = 8;
static const CGFloat JITTER_POS = 0.05;
static const CGFloat MARGIN = 80.0;
static const int AUTO_CLOSE_SECONDS = 10;

// -------- Helper Functions --------
struct RGB {
    uint8_t r, g, b;
    RGB(uint8_t _r = 0, uint8_t _g = 0, uint8_t _b = 0) : r(_r), g(_g), b(_b) {}
};

// Calculate average color of a region
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

// Calculate variance (standard deviation) of a region
double calculateVariance(NSBitmapImageRep *bitmap, int x, int y, int w, int h) {
    int x0 = std::max(0, x);
    int y0 = std::max(0, y);
    int x1 = std::min((int)[bitmap pixelsWide], x + w);
    int y1 = std::min((int)[bitmap pixelsHigh], y + h);
    
    if (x1 <= x0 || y1 <= y0) return 0.0;
    
    unsigned char *data = [bitmap bitmapData];
    int bpr = (int)[bitmap bytesPerRow];
    int bpp = (int)[bitmap bitsPerPixel] / 8;
    
    // Calculate mean
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
    
    // Calculate variance
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
        
        // TL, TR, BL, BR - same order as Python
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

// Build quadtree using BFS (same as Python)
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

// -------- Window Controller --------
@interface QuadtreeWindowController : NSObject
@property (nonatomic, strong) NSMutableArray<NSWindow*> *windows;
@property (nonatomic, strong) NSTimer *closeTimer;
@property (nonatomic) std::mt19937 rng;
@property (nonatomic) std::uniform_real_distribution<double> uni;
- (instancetype)initWithImagePath:(NSString *)path;
@end

@implementation QuadtreeWindowController

- (instancetype)initWithImagePath:(NSString *)path {
    self = [super init];
    if (!self) return nil;
    
    _windows = [NSMutableArray array];
    _rng.seed((uint32_t)CFAbsoluteTimeGetCurrent());
    _uni = std::uniform_real_distribution<double>(0.0, 1.0);
    
    // Load image
    NSImage *image = [[NSImage alloc] initWithContentsOfFile:path];
    if (!image) {
        NSLog(@"Failed to load image: %@", path);
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
        // Create bitmap from image
        NSSize size = [image size];
        [image lockFocus];
        bitmap = [[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(0, 0, size.width, size.height)];
        [image unlockFocus];
    }
    
    NSLog(@"Building quadtree...");
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
    
    CGFloat areaX0 = screenFrame.origin.x + (screenW - areaW) / 2;
    CGFloat areaY0 = screenFrame.origin.y + (screenH - areaH) / 2;
    
    CGFloat scaleX = areaW / imgW;
    CGFloat scaleY = areaH / imgH;
    
    // Create windows
    for (QuadNode *node : leaves) {
        CGFloat screenX = areaX0 + node->x * scaleX;
        CGFloat screenY = areaY0 + node->y * scaleY;
        CGFloat screenWNode = node->w * scaleX;
        CGFloat screenHNode = node->h * scaleY;
        
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
        
        // Set background color
        NSView *content = win.contentView;
        content.wantsLayer = YES;
        CGFloat r = node->color.r / 255.0;
        CGFloat g = node->color.g / 255.0;
        CGFloat b = node->color.b / 255.0;
        content.layer.backgroundColor = CGColorCreateGenericRGB(r, g, b, 1.0);
        
        [win orderFront:nil];
        [_windows addObject:win];
    }
    
    NSLog(@"Created %lu windows", (unsigned long)_windows.count);
    
    // Auto-close timer
    if (AUTO_CLOSE_SECONDS > 0) {
        _closeTimer = [NSTimer scheduledTimerWithTimeInterval:AUTO_CLOSE_SECONDS
                                                        target:self
                                                      selector:@selector(closeAllWindows)
                                                      userInfo:nil
                                                       repeats:NO];
    }
    
    return self;
}

- (void)closeAllWindows {
    for (NSWindow *win in _windows) {
        [win close];
    }
    [NSApp terminate:nil];
}

@end

// -------- App Delegate --------
@interface AppDelegate : NSObject <NSApplicationDelegate>
@property (nonatomic, strong) QuadtreeWindowController *controller;
@end

@implementation AppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    // Install event monitor for Escape key
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
        // Default to obama.jpg if no argument provided
        NSString *imagePath;
        if (argc < 2) {
            imagePath = @"obama.jpg";
            NSLog(@"No image specified, using default: obama.jpg");
        } else {
            imagePath = [NSString stringWithUTF8String:argv[1]];
        }
        
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        
        AppDelegate *delegate = [AppDelegate new];
        [NSApp setDelegate:delegate];
        
        delegate.controller = [[QuadtreeWindowController alloc] initWithImagePath:imagePath];
        if (!delegate.controller) {
            return 1;
        }
        
        [NSApp activateIgnoringOtherApps:YES];
        [NSApp run];
    }
    return 0;
}
