<?php
/**
 * Minimal security hardening for the personal blog.
 */

add_filter('xmlrpc_enabled', '__return_false');
remove_action('wp_head', 'wp_generator');

add_action('template_redirect', function () {
    if (is_author() && !is_admin()) {
        global $wp_query;
        $wp_query->set_404();
        status_header(404);
    }
});

add_action('init', function () {
    if (!is_admin() && isset($_GET['author'])) {
        wp_safe_redirect(home_url('/'), 301);
        exit;
    }
});
