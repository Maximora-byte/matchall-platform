<?php
/**
 * Plugin Name: MatchAll Blog Enhancements
 * Description: Local visual enhancements, language switcher, and anime Live2D widget for MatchAll Blog.
 * Version: 0.2.1
 * Author: MatchAll
 */

if (!defined('ABSPATH')) {
    exit;
}

define('MATCHALL_ENHANCEMENTS_VERSION', '0.2.1');
define('MATCHALL_ENHANCEMENTS_URL', plugin_dir_url(__FILE__));

function matchall_current_language_slug() {
    if (function_exists('pll_current_language')) {
        $language = pll_current_language('slug');
        if (!empty($language)) {
            return $language;
        }
    }

    return 'zh-cn';
}

function matchall_language_messages($language = null) {
    $language = $language ?: matchall_current_language_slug();

    $messages = array(
        'zh-cn' => array(
            'greeting' => '欢迎来到 MatchAll Blog',
            'notice' => 'Live2D 资源仅供研究学习，不得用于商业用途。',
            'short_notice' => '仅供研究学习，不得用于商业用途',
            'footer_notice' => 'Live2D 资源仅供研究学习，不得用于商业用途。',
            'touch' => array('别戳啦，去写点有趣的东西吧。', '今天也要认真折腾代码。', '换个模型看看？'),
            'skin' => array('切换看板娘', '新的角色已就位。'),
        ),
        'zh-tw' => array(
            'greeting' => '歡迎來到 MatchAll Blog',
            'notice' => 'Live2D 資源僅供研究學習，不得用於商業用途。',
            'short_notice' => '僅供研究學習，不得用於商業用途',
            'footer_notice' => 'Live2D 資源僅供研究學習，不得用於商業用途。',
            'touch' => array('別戳啦，去寫點有趣的東西吧。', '今天也要認真折騰程式。', '換個模型看看？'),
            'skin' => array('切換看板娘', '新的角色已就位。'),
        ),
        'en' => array(
            'greeting' => 'Welcome to MatchAll Blog',
            'notice' => 'Live2D assets are for research and learning only. No commercial use.',
            'short_notice' => 'Research and learning only. No commercial use.',
            'footer_notice' => 'Live2D assets are for research and learning only. No commercial use.',
            'touch' => array('Less poking, more building.', 'Ship something small today.', 'Try another model?'),
            'skin' => array('Switch character', 'New character online.'),
        ),
    );

    return isset($messages[$language]) ? $messages[$language] : $messages['zh-cn'];
}

add_filter('option_argon_footer_html', function () {
    $text = matchall_language_messages();

    return '<div><strong>MatchAll Blog</strong> · AI, Markets, Code, Notes</div><div>' . esc_html($text['footer_notice']) . '</div>';
});

add_action('wp_enqueue_scripts', function () {
    if (!is_admin()) {
        wp_enqueue_style(
            'matchall-pio-live2d',
            MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/pio.css',
            array(),
            MATCHALL_ENHANCEMENTS_VERSION
        );

        wp_enqueue_style(
            'matchall-enhancements',
            MATCHALL_ENHANCEMENTS_URL . 'assets/css/matchall.css',
            array('matchall-pio-live2d'),
            MATCHALL_ENHANCEMENTS_VERSION
        );

        wp_enqueue_script(
            'matchall-live2d-core',
            MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/live2dcubismcore.min.js',
            array(),
            MATCHALL_ENHANCEMENTS_VERSION,
            true
        );

        wp_enqueue_script(
            'matchall-live2d-pixi',
            MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/pixi.min.js',
            array('matchall-live2d-core'),
            MATCHALL_ENHANCEMENTS_VERSION,
            true
        );

        wp_enqueue_script(
            'matchall-live2d-cubism4',
            MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/cubism4.min.js',
            array('matchall-live2d-pixi'),
            MATCHALL_ENHANCEMENTS_VERSION,
            true
        );

        wp_enqueue_script(
            'matchall-live2d-tween',
            MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/TweenLite.js',
            array('matchall-live2d-cubism4'),
            MATCHALL_ENHANCEMENTS_VERSION,
            true
        );

        wp_enqueue_script(
            'matchall-live2d-pio-sdk',
            MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/pio_sdk4.js',
            array('matchall-live2d-tween'),
            MATCHALL_ENHANCEMENTS_VERSION,
            true
        );

        wp_enqueue_script(
            'matchall-live2d-pio',
            MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/pio.js',
            array('matchall-live2d-pio-sdk'),
            MATCHALL_ENHANCEMENTS_VERSION,
            true
        );

        wp_enqueue_script(
            'matchall-anime-live2d-init',
            MATCHALL_ENHANCEMENTS_URL . 'assets/js/anime-live2d-init.js',
            array('matchall-live2d-pio'),
            MATCHALL_ENHANCEMENTS_VERSION,
            true
        );

        wp_localize_script(
            'matchall-anime-live2d-init',
            'MatchAllLive2D',
            array(
                'assetBase' => MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/',
                'models' => array(
                    MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/Diana/Diana.model3.json',
                    MATCHALL_ENHANCEMENTS_URL . 'assets/live2d-cubism4/Ava/Ava.model3.json',
                ),
                'language' => matchall_current_language_slug(),
                'messages' => array(
                    'zh-cn' => matchall_language_messages('zh-cn'),
                    'zh-tw' => matchall_language_messages('zh-tw'),
                    'en' => matchall_language_messages('en'),
                ),
            )
        );
    }
});

add_action('wp_footer', function () {
    if (!function_exists('pll_the_languages')) {
        return;
    }

    $languages = pll_the_languages(array(
        'raw' => 1,
        'hide_if_empty' => 0,
        'hide_if_no_translation' => 0,
    ));

    if (empty($languages) || !is_array($languages)) {
        return;
    }
    ?>
    <div class="matchall-live2d-note" aria-label="Live2D usage notice">
        <strong>Live2D</strong>
        <span>
            <?php
            $text = matchall_language_messages();
            echo esc_html($text['short_notice']);
            ?>
        </span>
    </div>
    <nav class="matchall-language-switcher" aria-label="Language selector">
        <?php foreach ($languages as $language) : ?>
            <a class="<?php echo !empty($language['current_lang']) ? 'is-active' : ''; ?>"
               href="<?php echo esc_url($language['url']); ?>"
               lang="<?php echo esc_attr($language['locale']); ?>">
                <?php echo esc_html($language['name']); ?>
            </a>
        <?php endforeach; ?>
    </nav>
    <?php
});


add_action('template_redirect', function () {
    if (is_admin() || wp_doing_ajax()) {
        return;
    }

    $path = isset($_SERVER['REQUEST_URI']) ? strtok((string) $_SERVER['REQUEST_URI'], '?') : '';
    $path = trim($path, '/');
    $targets = array(
        'zh-cn' => '/zh-cn/home-zh-cn/',
        'zh-tw' => '/zh-tw/home-zh-tw/',
        'en' => '/en/home-en/',
    );

    if (isset($targets[$path])) {
        wp_safe_redirect(home_url($targets[$path]), 302);
        exit;
    }
});
