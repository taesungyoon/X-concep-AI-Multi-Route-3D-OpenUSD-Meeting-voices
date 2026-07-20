<?php
declare(strict_types=1);

final class ControlPlaneClient
{
    public function __construct(private readonly string $baseUrl)
    {
    }

    public function proxy(string $method, string $path): never
    {
        $url = $this->baseUrl . $path;
        $query = $_SERVER['QUERY_STRING'] ?? '';
        if ($query !== '') {
            $url .= '?' . $query;
        }
        if (!function_exists('curl_init')) {
            throw new RuntimeException('PHP cURL 확장이 필요함');
        }
        $ch = curl_init($url);
        $headers = ['Accept: application/json'];
        $body = null;
        $contentType = $_SERVER['CONTENT_TYPE'] ?? '';
        if (str_starts_with(strtolower($contentType), 'multipart/form-data')) {
            $payload = $_POST;
            foreach ($_FILES as $key => $file) {
                if (is_array($file['name'] ?? null)) {
                    foreach ($file['name'] as $i => $name) {
                        if (($file['error'][$i] ?? UPLOAD_ERR_NO_FILE) === UPLOAD_ERR_OK) {
                            $payload[$key . '[' . $i . ']'] = new CURLFile(
                                $file['tmp_name'][$i],
                                $file['type'][$i] ?: 'application/octet-stream',
                                $name
                            );
                        }
                    }
                } elseif (($file['error'] ?? UPLOAD_ERR_NO_FILE) === UPLOAD_ERR_OK) {
                    $payload[$key] = new CURLFile(
                        $file['tmp_name'],
                        $file['type'] ?: 'application/octet-stream',
                        $file['name'] ?: 'upload.bin'
                    );
                }
            }
            $body = $payload;
        } else {
            $raw = file_get_contents('php://input');
            if ($raw !== false && $raw !== '') {
                $body = $raw;
                $headers[] = 'Content-Type: ' . ($contentType ?: 'application/json');
            }
        }
        curl_setopt_array($ch, [
            CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_CONNECTTIMEOUT => 15,
            CURLOPT_TIMEOUT => 3600,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_HEADER => true,
        ]);
        if ($body !== null && !in_array($method, ['GET', 'HEAD'], true)) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        }
        $response = curl_exec($ch);
        if ($response === false) {
            $error = curl_error($ch);
            curl_close($ch);
            throw new RuntimeException('DRF Control Plane 연결 실패: ' . $error);
        }
        $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        $headerSize = (int)curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        $responseHeaders = substr($response, 0, $headerSize);
        $responseBody = substr($response, $headerSize);
        curl_close($ch);
        http_response_code($status ?: 502);
        foreach (preg_split('/\r\n|\r|\n/', $responseHeaders) as $line) {
            if (stripos($line, 'content-type:') === 0 || stripos($line, 'content-disposition:') === 0) {
                header($line);
            }
        }
        if (!headers_sent() && !preg_match('/^\s*</', $responseBody)) {
            header('Content-Type: application/json; charset=utf-8');
        }
        echo $responseBody;
        exit;
    }
}
