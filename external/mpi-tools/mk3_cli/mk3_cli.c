#include "mk3.h"
#include "mk3_display.h"
#include "mk3_internal.h"
#include <ft2build.h>
#include FT_FREETYPE_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>

#define WIDTH 480
#define HEIGHT 272

#define FONT_SANS "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
#define FONT_MONO "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

void draw_text_rgb565(uint16_t* buf, const char* msg, int x, int y,
                      int font_size, const char* font_path,
                      uint8_t cr, uint8_t cg, uint8_t cb) {
    FT_Library ft;
    FT_Face face;
    if (FT_Init_FreeType(&ft)) return;
    if (FT_New_Face(ft, font_path, 0, &face)) {
        FT_Done_FreeType(ft);
        return;
    }
    FT_Set_Pixel_Sizes(face, 0, font_size);

    int pen_x = x, pen_y = y;
    int line_height = font_size + 2;

    for (size_t i = 0; i < strlen(msg); i++) {
        if (msg[i] == '\n') {
            pen_x = x;
            pen_y += line_height;
            continue;
        }

        if (FT_Load_Char(face, msg[i], FT_LOAD_RENDER)) continue;
        FT_GlyphSlot g = face->glyph;

        for (int row = 0; row < (int)g->bitmap.rows; row++) {
            for (int col = 0; col < (int)g->bitmap.width; col++) {
                int px = pen_x + g->bitmap_left + col;
                int py = pen_y - g->bitmap_top + row;
                if (px < 0 || py < 0 || px >= WIDTH || py >= HEIGHT) continue;

                uint8_t val = g->bitmap.buffer[row * g->bitmap.pitch + col];
                if (val == 0) continue;
                uint8_t r = (cr * val) / 255;
                uint8_t g_ = (cg * val) / 255;
                uint8_t b = (cb * val) / 255;
                buf[py * WIDTH + px] = ((r & 0xF8) << 8) | ((g_ & 0xFC) << 3) | (b >> 3);
            }
        }

        pen_x += g->advance.x >> 6;
    }

    FT_Done_Face(face);
    FT_Done_FreeType(ft);
}

int main(int argc, char** argv) {
    const char* msg = NULL;
    int target = 0; // default: left
    int clear_display = 0;
    int use_pipe = 0;
    int loop_fps = 0;
    int disable_partial_rendering = 0;
    int font_size = 24;
    int use_mono = 0;
    uint8_t color_r = 255, color_g = 255, color_b = 255;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--text") && i + 1 < argc) {
            msg = argv[++i];
        } else if (!strcmp(argv[i], "--target") && i + 1 < argc) {
            const char* t = argv[++i];
            if (!strcmp(t, "right")) target = 1;
            else if (!strcmp(t, "both")) target = 2;
            else if (!strcmp(t, "left")) target = 0;
            else {
                fprintf(stderr, "Unknown target: %s\n", t);
                return 1;
            }
        } else if (!strcmp(argv[i], "--clear-display")) {
            clear_display = 1;
        } else if (!strcmp(argv[i], "--pipe")) {
            use_pipe = 1;
        } else if (!strcmp(argv[i], "--loop") && i + 1 < argc) {
            loop_fps = atoi(argv[++i]);
            if (loop_fps <= 0 || loop_fps > 240) {
                fprintf(stderr, "Invalid --loop FPS value\n");
                return 1;
            }
        } else if (!strcmp(argv[i], "--disable-partial")) {
            disable_partial_rendering = 1;
        } else if (!strcmp(argv[i], "--font-size") && i + 1 < argc) {
            font_size = atoi(argv[++i]);
            if (font_size <= 0 || font_size > 120) {
                fprintf(stderr, "Invalid --font-size value (1-120)\n");
                return 1;
            }
        } else if (!strcmp(argv[i], "--mono")) {
            use_mono = 1;
        } else if (!strcmp(argv[i], "--color") && i + 1 < argc) {
            unsigned int hex = (unsigned int)strtol(argv[++i], NULL, 16);
            color_r = (hex >> 16) & 0xFF;
            color_g = (hex >> 8) & 0xFF;
            color_b = hex & 0xFF;
        }
    }

    mk3_t* dev = mk3_open();
    if (!dev) return 1;

    dev->disable_partial_rendering = disable_partial_rendering;

    if (clear_display) {
        if (target == 0 || target == 2) mk3_display_clear(dev, 0, 0x0000);
        if (target == 1 || target == 2) mk3_display_clear(dev, 1, 0x0000);
        mk3_close(dev);
        return 0;
    }

    if (use_pipe) {
        size_t frame_bytes = WIDTH * HEIGHT * 2;
        uint16_t* buf = malloc(frame_bytes);
        if (!buf) {
            fprintf(stderr, "Failed to allocate frame buffer\n");
            mk3_close(dev);
            return 1;
        }

        const int sleep_us = (loop_fps > 0) ? (1000000 / loop_fps) : 0;

        while (1) {
            size_t got = fread(buf, 1, frame_bytes, stdin);
            if (got != frame_bytes) break;

            if (target == 0 || target == 2) mk3_display_draw(dev, 0, buf);
            if (target == 1 || target == 2) mk3_display_draw(dev, 1, buf);

            if (sleep_us > 0) usleep(sleep_us);
        }

        free(buf);
        mk3_close(dev);
        return 0;
    }

    if (!msg) {
        fprintf(stderr, "Usage:\n");
        fprintf(stderr, "  %s --text \"Hello\" [--target left|right|both] [--font-size N] [--mono] [--color RRGGBB]\n", argv[0]);
        fprintf(stderr, "  %s --clear-display [--target left|right|both]\n", argv[0]);
        fprintf(stderr, "  %s --pipe [--target left|right|both] [--loop fps] < raw565\n", argv[0]);
        return 1;
    }

    const char* font_path = use_mono ? FONT_MONO : FONT_SANS;
    uint16_t* frame = calloc(WIDTH * HEIGHT, sizeof(uint16_t));
    draw_text_rgb565(frame, msg, 8, font_size + 2, font_size, font_path,
                     color_r, color_g, color_b);

    if (target == 0 || target == 2) mk3_display_draw(dev, 0, frame);
    if (target == 1 || target == 2) mk3_display_draw(dev, 1, frame);

    free(frame);
    mk3_close(dev);
    return 0;
}
