<?php
declare(strict_types=1);

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$public = __DIR__ . DIRECTORY_SEPARATOR . 'public';
$candidate = realpath($public . DIRECTORY_SEPARATOR . ltrim($path, '/'));
$root = realpath($public);
if ($path !== '/' && $candidate !== false && $root !== false
    && str_starts_with($candidate, $root . DIRECTORY_SEPARATOR) && is_file($candidate)) {
    return false;
}
require $public . DIRECTORY_SEPARATOR . 'index.php';
