#include <GLFW/glfw3.h>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <random>
#include <thread>
#include <vector>
#include <algorithm>

/*
g++ -std=c++17 -O2 main.cpp -o window_stress \
  $(pkg-config --cflags --libs glfw3) \
  -framework OpenGL
*/

struct Win {
    GLFWwindow* handle{};
    float r{}, g{}, b{};
    int x{}, y{}, w{}, h{};
};

static bool g_quit = false;

static void key_callback(GLFWwindow* window, int key, int scancode, int action, int mods) {
    (void)scancode; (void)mods;
    if (action == GLFW_PRESS) {
        if (key == GLFW_KEY_ESCAPE || key == GLFW_KEY_Q) {
            g_quit = true;
        }
    }
}

int main() {

    glfwWindowHint(GLFW_COCOA_RETINA_FRAMEBUFFER, GLFW_FALSE);
    glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE);

    const int WINDOW_COUNT = 100;
    const double TARGET_FPS = 60.0;     // set to 10.0 if you only need >=10 fps
    const int MIN_SIZE = 80;
    const int MAX_SIZE = 220;
    const int JITTER_POS = 8;
    const int JITTER_SIZE = 40;

    if (!glfwInit()) {
        std::fprintf(stderr, "Failed to init GLFW\n");
        return 1;
    }

    // We want standard titled, resizable macOS windows.
    glfwWindowHint(GLFW_DECORATED, GLFW_TRUE);
    glfwWindowHint(GLFW_RESIZABLE, GLFW_TRUE);
    glfwWindowHint(GLFW_VISIBLE, GLFW_TRUE);
    glfwWindowHint(GLFW_DOUBLEBUFFER, GLFW_TRUE);

    // Disable vsync so our timer controls the frame rate across many windows.
    // We'll set this per-context after creation.
    // (If you prefer vsync per window, set to 1 instead.)
    std::mt19937 rng{static_cast<uint32_t>(
        std::chrono::high_resolution_clock::now().time_since_epoch().count()
    )};
    std::uniform_real_distribution<float> uni01(0.f, 1.f);
    std::uniform_int_distribution<int> jitterPos(-JITTER_POS, JITTER_POS);
    std::uniform_int_distribution<int> jitterSize(-JITTER_SIZE, JITTER_SIZE);
    std::uniform_int_distribution<int> sizeRand(MIN_SIZE, MAX_SIZE);

    // Determine usable work area (excludes menu bar/dock where possible)
    GLFWmonitor* primary = glfwGetPrimaryMonitor();
    int workX=0, workY=0, workW=0, workH=0;
#if GLFW_VERSION_MAJOR >= 3
    // Requires GLFW 3.3+: provides monitor work area.
    glfwGetMonitorWorkarea(primary, &workX, &workY, &workW, &workH);
#else
    // Fallback: use video mode (may include areas under menu/dock)
    const GLFWvidmode* mode = glfwGetVideoMode(primary);
    workW = mode->width;
    workH = mode->height;
#endif

    // Create windows
    std::vector<Win> wins;
    wins.reserve(WINDOW_COUNT);

    for (int i = 0; i < WINDOW_COUNT; ++i) {
        int w = sizeRand(rng);
        int h = sizeRand(rng);
        int x = workX + (int)(uni01(rng) * std::max(1, workW - w));
        int y = workY + (int)(uni01(rng) * std::max(1, workH - h));

        // Create the window
        GLFWwindow* win = glfwCreateWindow(w, h, ("Window " + std::to_string(i+1)).c_str(), nullptr, nullptr);
        if (!win) {
            std::fprintf(stderr, "Failed to create window %d\n", i+1);
            break;
        }

        // Position it
        glfwSetWindowPos(win, x, y);

        // Hook keys (Q/Esc to quit)
        glfwSetKeyCallback(win, key_callback);

        // Give each window a random solid color
        float r = uni01(rng), g = uni01(rng), b = uni01(rng);

        // Set up its GL context and turn off vsync
        glfwMakeContextCurrent(win);
        glfwSwapInterval(0); // no vsync; we drive FPS ourselves

        wins.push_back(Win{win, r, g, b, x, y, w, h});
    }

    // Main loop: draw, jiggle, clamp to target FPS
    using clock = std::chrono::high_resolution_clock;
    const double dt_target = 1.0 / TARGET_FPS;

    while (!g_quit) {
        auto frameStart = clock::now();

        glfwPollEvents(); // process close buttons, keypresses, etc.

        // Update + render each window
        for (auto& w : wins) {
            if (glfwWindowShouldClose(w.handle)) {
                g_quit = true;
                break;
            }

            // Random jitter in position/size
            int dw = jitterSize(rng);
            int dh = jitterSize(rng);
            int dx = jitterPos(rng);
            int dy = jitterPos(rng);

            int newW = std::clamp(w.w + dw, MIN_SIZE, MAX_SIZE);
            int newH = std::clamp(w.h + dh, MIN_SIZE, MAX_SIZE);

            int newX = std::clamp(w.x + dx, workX, workX + workW - newW);
            int newY = std::clamp(w.y + dy, workY, workY + workH - newH);

            // Apply new frame (pos + size)
            if (newW != w.w || newH != w.h)
                glfwSetWindowSize(w.handle, newW, newH);
            if (newX != w.x || newY != w.y)
                glfwSetWindowPos(w.handle, newX, newY);

            w.w = newW; w.h = newH;
            w.x = newX; w.y = newY;

            // Render solid color
            glfwMakeContextCurrent(w.handle);
            glViewport(0, 0, w.w, w.h);
            glClearColor(w.r, w.g, w.b, 1.0f);
            glClear(GL_COLOR_BUFFER_BIT);
            glfwSwapBuffers(w.handle);
        }

        // Simple frame pacing
        auto frameEnd = clock::now();
        std::chrono::duration<double> elapsed = frameEnd - frameStart;
        double sleepSec = dt_target - elapsed.count();
        if (sleepSec > 0.0) {
            std::this_thread::sleep_for(std::chrono::duration<double>(sleepSec));
        }
    }

    // Cleanup
    for (auto& w : wins) {
        if (w.handle) glfwDestroyWindow(w.handle);
    }
    glfwTerminate();
    return 0;
}
