<?php
declare(strict_types=1);

namespace CadAi\Tests;

final class ValidationSupport
{
    public static function sourceHash(string $root): string
    {
        $files = [];
        foreach (['src', 'tests', 'schemas', 'public'] as $directory) {
            $iterator = new \RecursiveIteratorIterator(
                new \RecursiveDirectoryIterator($root . '/' . $directory, \FilesystemIterator::SKIP_DOTS)
            );
            foreach ($iterator as $file) {
                if ($file->isFile()) {
                    $files[] = $file->getPathname();
                }
            }
        }
        sort($files);
        $context = hash_init('sha256');
        foreach ($files as $file) {
            hash_update($context, str_replace('\\', '/', substr($file, strlen($root) + 1)));
            hash_update($context, "\0");
            hash_update_file($context, $file);
            hash_update($context, "\0");
        }
        return hash_final($context);
    }

    public static function removeTree(string $target, string $allowedRoot): void
    {
        $target = realpath($target);
        $root = realpath($allowedRoot);
        if ($target === false || $root === false || !str_starts_with($target, $root . DIRECTORY_SEPARATOR)) {
            throw new \RuntimeException('검증 작업 경로가 안전하지 않습니다.');
        }
        $iterator = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($target, \FilesystemIterator::SKIP_DOTS),
            \RecursiveIteratorIterator::CHILD_FIRST
        );
        foreach ($iterator as $item) {
            $item->isDir() ? rmdir($item->getPathname()) : unlink($item->getPathname());
        }
        rmdir($target);
    }
}
