<?php
declare(strict_types=1);

final class Config
{
    public static function controlPlaneUrl(): string
    {
        return rtrim((string)(getenv('CONTROL_PLANE_URL') ?: 'http://control-plane:8000'), '/');
    }

    public static function maxUploadBytes(): int
    {
        $mb = max(1, (int)(getenv('MAX_UPLOAD_MB') ?: 128));
        return $mb * 1024 * 1024;
    }

    public static function controlPlaneToken(): string
    {
        return trim((string)(getenv('CONTROL_PLANE_TOKEN') ?: ''));
    }
}
