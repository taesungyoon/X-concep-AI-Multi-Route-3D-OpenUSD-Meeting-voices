<?php
declare(strict_types=1);

namespace CadAi\Parsers;

final class StepParser
{
    public function parse(string $path): array
    {
        $content = file_get_contents($path);
        if ($content === false) {
            throw new \RuntimeException('STEP을 읽을 수 없습니다.');
        }
        preg_match_all('/#\d+\s*=\s*([A-Z0-9_]+)\s*\(/i', $content, $matches);
        $counts = [];
        foreach ($matches[1] ?? [] as $type) {
            $type = strtoupper($type);
            $counts[$type] = ($counts[$type] ?? 0) + 1;
        }
        ksort($counts);

        preg_match_all("/PRODUCT\\s*\\(\\s*'([^']*)'\\s*,\\s*'([^']*)'/i", $content, $productMatches, PREG_SET_ORDER);
        $products = [];
        foreach ($productMatches as $match) {
            $name = trim($match[2] !== '' ? $match[2] : $match[1]);
            if ($name !== '') {
                $products[] = $name;
            }
        }
        preg_match_all('/CARTESIAN_POINT\s*\([^,]*,\s*\(\s*([^)]+)\)\s*\)/i', $content, $pointMatches);
        $points = [];
        foreach ($pointMatches[1] ?? [] as $raw) {
            $numbers = array_values(array_filter(array_map('trim', explode(',', $raw)), 'is_numeric'));
            if (count($numbers) >= 2) {
                $points[] = [
                    (float)$numbers[0],
                    (float)$numbers[1],
                    isset($numbers[2]) ? (float)$numbers[2] : 0.0,
                ];
            }
        }

        $sumTypes = static function (array $needles) use ($counts): int {
            $total = 0;
            foreach ($counts as $type => $count) {
                foreach ($needles as $needle) {
                    if (str_contains($type, $needle)) {
                        $total += $count;
                        break;
                    }
                }
            }
            return $total;
        };

        return [
            'parser_mode' => 'php_part21_step_v1',
            'entity_counts' => $counts,
            'products' => array_values(array_unique($products)),
            'points' => $points,
            'bbox' => Geometry::bbox($points),
            'topology' => [
                'edge_count' => $sumTypes(['EDGE']),
                'face_count' => $sumTypes(['FACE']),
                'shell_count' => $sumTypes(['SHELL']),
                'solid_count' => $sumTypes(['SOLID', 'BREP']),
            ],
            'surfaces' => [
                'plane' => $sumTypes(['PLANE']),
                'cylinder' => $sumTypes(['CYLINDRICAL_SURFACE']),
                'cone' => $sumTypes(['CONICAL_SURFACE']),
                'sphere' => $sumTypes(['SPHERICAL_SURFACE']),
                'torus' => $sumTypes(['TOROIDAL_SURFACE']),
                'bspline' => $sumTypes(['B_SPLINE_SURFACE']),
            ],
            'warnings' => $counts === [] ? ['no_step_entities'] : [],
        ];
    }
}
