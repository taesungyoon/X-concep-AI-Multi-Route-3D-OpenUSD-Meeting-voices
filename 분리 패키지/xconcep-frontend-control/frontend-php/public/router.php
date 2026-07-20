<?php
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$sensitive = [
    '#^/storage/projects/[^/]+/(project\.json|analysis\.json|design_state\.json|generation_plan\.json|reference-contact-sheet\.png)$#',
    '#^/storage/projects/[^/]+/(uploads|meeting)(/|$)#',
];
foreach ($sensitive as $pattern) {
    if (preg_match($pattern, $path)) {
        http_response_code(403);
        header('Content-Type: text/plain; charset=utf-8');
        echo 'Forbidden';
        return true;
    }
}
$file = __DIR__ . $path;
if ($path !== '/' && is_file($file)) {
    return false;
}
require __DIR__ . '/index.php';
