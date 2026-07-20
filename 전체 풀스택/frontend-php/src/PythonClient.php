<?php
declare(strict_types=1);

final class PythonClient
{
    public function __construct(private readonly string $baseUrl)
    {
    }

    public function health(): array
    {
        return $this->get('/health', 10);
    }

    public function generate2d(array $payload): array
    {
        return $this->post('/v1/generate/2d', $payload, 900);
    }

    public function generate3d(array $payload): array
    {
        return $this->post('/v1/generate/3d', $payload, 2100);
    }

    public function transcribeMeeting(array $payload): array
    {
        return $this->post('/v1/meeting/transcribe', $payload, 420);
    }

    public function analyzeMeeting(array $payload): array
    {
        return $this->post('/v1/meeting/analyze', $payload, 420);
    }

    public function patchMeeting(array $payload): array
    {
        return $this->post('/v1/meeting/patch', $payload, 420);
    }

    private function get(string $path, int $timeout): array
    {
        $url = $this->baseUrl . $path;
        $context = stream_context_create(['http' => ['method' => 'GET', 'timeout' => $timeout, 'ignore_errors' => true]]);
        $response = file_get_contents($url, false, $context);
        if ($response === false) {
            throw new RuntimeException('Python Worker 연결 실패');
        }
        return json_decode($response, true, 512, JSON_THROW_ON_ERROR);
    }

    private function post(string $path, array $payload, int $timeout): array
    {
        $url = $this->baseUrl . $path;
        $json = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);

        if (function_exists('curl_init')) {
            $ch = curl_init($url);
            curl_setopt_array($ch, [
                CURLOPT_POST => true,
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
                CURLOPT_POSTFIELDS => $json,
                CURLOPT_CONNECTTIMEOUT => 15,
                CURLOPT_TIMEOUT => $timeout,
            ]);
            $response = curl_exec($ch);
            $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
            $error = curl_error($ch);
            curl_close($ch);
            if ($response === false || $status >= 400) {
                throw new RuntimeException('Python Worker 요청 실패: ' . ($error ?: (string)$response));
            }
            return json_decode((string)$response, true, 512, JSON_THROW_ON_ERROR);
        }

        $context = stream_context_create(['http' => [
            'method' => 'POST',
            'header' => "Content-Type: application/json\r\n",
            'content' => $json,
            'timeout' => $timeout,
            'ignore_errors' => true,
        ]]);
        $response = file_get_contents($url, false, $context);
        if ($response === false) {
            throw new RuntimeException('Python Worker 연결 실패');
        }
        return json_decode($response, true, 512, JSON_THROW_ON_ERROR);
    }
}
