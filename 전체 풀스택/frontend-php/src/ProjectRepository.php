<?php
declare(strict_types=1);

final class ProjectRepository
{
    public function __construct(private readonly string $storagePath)
    {
        $this->ensureDirectory($this->projectsPath());
    }

    public function create(string $prompt, string $category, array $images): array
    {
        $id = 'PRJ-' . strtoupper(bin2hex(random_bytes(5)));
        $now = gmdate('c');
        $project = [
            'id' => $id,
            'prompt' => $prompt,
            'category' => $category,
            'source_images' => $images,
            'status' => 'created',
            'progress' => 0,
            'step' => 'input',
            'results_2d' => [],
            'selected_2d_id' => null,
            'result_3d' => null,
            'revision' => 1,
            'meeting' => [
                'status' => 'idle',
                'segments' => [],
                'transcript' => '',
                'analysis' => null,
                'chunk_count' => 0,
            ],
            'created_at' => $now,
            'updated_at' => $now,
        ];
        $this->save($project);
        return $project;
    }

    public function find(string $id): ?array
    {
        $file = $this->projectFile($id);
        if (!is_file($file)) {
            return null;
        }
        $data = json_decode((string)file_get_contents($file), true);
        return is_array($data) ? $data : null;
    }

    public function save(array $project): void
    {
        if (!isset($project['id'])) {
            throw new InvalidArgumentException('프로젝트 ID가 없음');
        }
        $project['updated_at'] = gmdate('c');
        $dir = $this->projectPath((string)$project['id']);
        $this->ensureDirectory($dir);
        file_put_contents(
            $this->projectFile((string)$project['id']),
            json_encode($project, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
            LOCK_EX
        );
    }

    public function list(int $limit = 20): array
    {
        $files = glob($this->projectsPath() . '/*/project.json') ?: [];
        $items = [];
        foreach ($files as $file) {
            $data = json_decode((string)file_get_contents($file), true);
            if (is_array($data)) {
                $items[] = $data;
            }
        }
        usort($items, fn(array $a, array $b) => strcmp((string)$b['updated_at'], (string)$a['updated_at']));
        return array_slice($items, 0, $limit);
    }

    public function projectPath(string $id): string
    {
        return $this->projectsPath() . '/' . basename($id);
    }

    private function projectsPath(): string
    {
        return $this->storagePath . '/projects';
    }

    private function projectFile(string $id): string
    {
        return $this->projectPath($id) . '/project.json';
    }

    private function ensureDirectory(string $path): void
    {
        if (!is_dir($path) && !mkdir($path, 0775, true) && !is_dir($path)) {
            throw new RuntimeException('디렉터리 생성 실패: ' . $path);
        }
    }
}
