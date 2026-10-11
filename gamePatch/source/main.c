// gamePatch/source/main.c
/**
 * Miitalkmo Game Patch - Main Hook
 * Custom TTS integration for Miitomo-style voice synthesis
 * Supports 12 languages and custom voice parameters
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mem.h"
#include "tomoFunc.h"
#include "tomoStructs.h"

// Language codes
typedef enum {
    LANG_JAPANESE = 0,
    LANG_ENGLISH_US = 1,
    LANG_FRENCH_EU = 2,
    LANG_GERMAN = 3,
    LANG_ITALIAN = 4,
    LANG_SPANISH_EU = 5,
    LANG_SPANISH_LA = 6,
    LANG_DUTCH = 7,
    LANG_PORTUGUESE = 8,
    LANG_RUSSIAN = 9,
    LANG_KOREAN = 10,
    LANG_CHINESE_SIMP = 11,
    LANG_CHINESE_TRAD = 12,
    LANG_FINNISH = 13,
    LANG_SWEDISH = 14,
    LANG_DANISH = 15,
    LANG_NORWEGIAN = 16,
    LANG_ARABIC = 17,
    LANG_CATALAN = 18,
    LANG_UKRAINIAN = 19,
} Language;

// Voice parameter structure (matching Miitomo 5-dot system)
typedef struct {
    unsigned char pitch;      // 0-100
    unsigned char depth;      // 0-100
    unsigned char energy;     // 0-100
    unsigned char accent;     // 0-100
    unsigned char speed;      // 0-100
} VoiceParams;

// TTS request structure
typedef struct {
    char text[512];
    VoiceParams voice;
    unsigned char language;
    unsigned char padding[3];
} TTSRequest;

// TTS response structure
typedef struct {
    unsigned char status;     // 0=idle, 1=processing, 2=ready, 3=error
    unsigned char reserved[3];
    unsigned int audio_size;
    unsigned int audio_ptr;
} TTSResponse;

// =====================================================
// Global state
// =====================================================
static VoiceParams g_current_voice = {50, 50, 50, 50, 50};
static Language g_current_language = LANG_JAPANESE;
static unsigned char g_tts_enabled = 1;

// =====================================================
// Language support
// =====================================================
const char* language_codes[] = {
    "ja_JP",      // LANG_JAPANESE
    "en_US",      // LANG_ENGLISH_US
    "fr_FR",      // LANG_FRENCH_EU
    "de_DE",      // LANG_GERMAN
    "it_IT",      // LANG_ITALIAN
    "es_ES",      // LANG_SPANISH_EU
    "es_MX",      // LANG_SPANISH_LA
    "nl_NL",      // LANG_DUTCH
    "pt_BR",      // LANG_PORTUGUESE
    "ru_RU",      // LANG_RUSSIAN
    "ko_KR",      // LANG_KOREAN
    "zh_CN",      // LANG_CHINESE_SIMP
    "zh_TW",      // LANG_CHINESE_TRAD
    "fi_FI",      // LANG_FINNISH
    "sv_SE",      // LANG_SWEDISH
    "da_DK",      // LANG_DANISH
    "nb_NO",      // LANG_NORWEGIAN
    "ar_SA",      // LANG_ARABIC
    "ca_ES",      // LANG_CATALAN
    "uk_UA",      // LANG_UKRAINIAN
};

const char* get_language_code(Language lang) {
    if (lang < 0 || lang >= 20) {
        return language_codes[LANG_JAPANESE];
    }
    return language_codes[lang];
}

// =====================================================
// Voice parameter utilities
// =====================================================
void set_voice_params(VoiceParams params) {
    g_current_voice.pitch = params.pitch % 101;
    g_current_voice.depth = params.depth % 101;
    g_current_voice.energy = params.energy % 101;
    g_current_voice.accent = params.accent % 101;
    g_current_voice.speed = params.speed % 101;
}

VoiceParams get_voice_params(void) {
    return g_current_voice;
}

void set_language(Language lang) {
    if (lang >= 0 && lang < 20) {
        g_current_language = lang;
    }
}

Language get_language(void) {
    return g_current_language;
}

// =====================================================
// TTS Engine Hook
// =====================================================
void tts_synthesize(TTSRequest* request, TTSResponse* response) {
    if (!g_tts_enabled || !request || !response) {
        if (response) {
            response->status = 3;  // error
        }
        return;
    }

    // Validate text
    if (request->text[0] == '\0') {
        response->status = 3;
        return;
    }

    // Set status to processing
    response->status = 1;

    // Apply voice parameters
    set_voice_params(request->voice);
    set_language(request->language);

    // Call the original TTS setup
    #ifndef REGION_JP
    setupTTS();
    #endif

    // Get TTS global state
    ttsGlobal* tts = getTtsGlobal();
    if (!tts) {
        response->status = 3;
        return;
    }

    #ifndef REGION_JP
    // Apply voice settings to the TTS engine
    if (tts->mainTtsClass) {
        ttsClass* tts_obj = tts->mainTtsClass;
        
        // Apply pitch adjustment
        // This is a simplified example - actual pitch control depends on Nuance API
        unsigned int pitch_scaled = (request->voice.pitch * 150) / 100;
        
        // Apply speed adjustment
        unsigned int speed_scaled = (request->voice.speed * 150) / 100;
        
        // Apply energy/volume adjustment
        unsigned int energy_scaled = (request->voice.energy * 100) / 100;
    }
    #endif

    // Mark as ready
    response->status = 2;
}

// =====================================================
// Miitalkmo API Hooks
// =====================================================

/**
 * Hook: Set current voice profile
 * Call: miitalkmo_set_voice(pitch, depth, energy, accent, speed)
 */
void miitalkmo_set_voice(unsigned char pitch, unsigned char depth, 
                         unsigned char energy, unsigned char accent, 
                         unsigned char speed) {
    VoiceParams params;
    params.pitch = pitch;
    params.depth = depth;
    params.energy = energy;
    params.accent = accent;
    params.speed = speed;
    set_voice_params(params);
}

/**
 * Hook: Get current voice profile
 * Returns: VoiceParams structure
 */
VoiceParams miitalkmo_get_voice(void) {
    return get_voice_params();
}

/**
 * Hook: Set language
 * Call: miitalkmo_set_language(language_code)
 */
void miitalkmo_set_language(unsigned char language) {
    set_language((Language)language);
}

/**
 * Hook: Get language code
 * Returns: Language code string (e.g., "en_US")
 */
const char* miitalkmo_get_language_code(void) {
    return get_language_code(g_current_language);
}

/**
 * Hook: Enable/disable TTS
 */
void miitalkmo_set_enabled(unsigned char enabled) {
    g_tts_enabled = enabled ? 1 : 0;
}

/**
 * Hook: Get TTS enabled status
 */
unsigned char miitalkmo_is_enabled(void) {
    return g_tts_enabled;
}

/**
 * Hook: Synthesize text (wrapper)
 */
void miitalkmo_synthesize(const char* text, VoiceParams voice, 
                          unsigned char language, 
                          TTSResponse* response) {
    TTSRequest request;
    
    // Copy text (with bounds checking)
    strncpy(request.text, text ? text : "", sizeof(request.text) - 1);
    request.text[sizeof(request.text) - 1] = '\0';
    
    request.voice = voice;
    request.language = language;
    
    tts_synthesize(&request, response);
}

// =====================================================
// Initialization
// =====================================================
void miitalkmo_init(void) {
    // Initialize TTS engine
    #ifndef REGION_JP
    setupTTS();
    #endif
    
    // Set default language based on region
    #ifdef REGION_JP
    g_current_language = LANG_JAPANESE;
    #elif defined(REGION_EU)
    g_current_language = LANG_ENGLISH_US;
    #elif defined(REGION_KR)
    g_current_language = LANG_KOREAN;
    #else
    g_current_language = LANG_ENGLISH_US;
    #endif
    
    // Set default voice
    g_current_voice.pitch = 50;
    g_current_voice.depth = 50;
    g_current_voice.energy = 50;
    g_current_voice.accent = 50;
    g_current_voice.speed = 50;
    
    g_tts_enabled = 1;
}

// =====================================================
// Cleanup
// =====================================================
void miitalkmo_cleanup(void) {
    g_tts_enabled = 0;
}

// =====================================================
// Main entry point (called by loader)
// =====================================================
int main(void) {
    miitalkmo_init();
    return 0;
}
