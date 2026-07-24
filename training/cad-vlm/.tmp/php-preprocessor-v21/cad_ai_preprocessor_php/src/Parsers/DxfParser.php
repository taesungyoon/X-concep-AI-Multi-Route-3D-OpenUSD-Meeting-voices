<?php
declare(strict_types=1);

namespace CadAi\Parsers;

final class DxfParser
{
    public function parse(string $path): array
    {
        $lines = file($path, FILE_IGNORE_NEW_LINES);
        if ($lines === false) {
            throw new \RuntimeException('DXF를 읽을 수 없습니다.');
        }
        $sourceEncoding = self::sourceEncoding($lines);
        $pairs = [];
        for ($i = 0, $count = count($lines) - 1; $i < $count; $i += 2) {
            $pairs[] = [
                trim($lines[$i]),
                self::utf8(trim($lines[$i + 1]), $sourceEncoding),
            ];
        }
        $entityTypes = [
            'LINE', 'CIRCLE', 'ARC', 'LWPOLYLINE', 'POLYLINE', 'VERTEX',
            'TEXT', 'MTEXT', 'INSERT', 'DIMENSION', 'POINT', 'SPLINE',
        ];
        $counts = [];
        $layers = [];
        $texts = [];
        $points = [];
        $primitives = [];
        $inEntities = false;
        $current = null;

        $flush = static function (?array $entity) use (&$counts, &$layers, &$texts, &$points, &$primitives): void {
            if ($entity === null) {
                return;
            }
            $type = $entity['type'];
            $counts[$type] = ($counts[$type] ?? 0) + 1;
            $layer = $entity['values']['8'][0] ?? '0';
            $layers[$layer] = ($layers[$layer] ?? 0) + 1;
            foreach (['1', '3'] as $textCode) {
                foreach ($entity['values'][$textCode] ?? [] as $text) {
                    if (in_array($type, ['TEXT', 'MTEXT', 'DIMENSION'], true) && $text !== '') {
                        $texts[] = $text;
                    }
                }
            }
            $xCodes = ['10', '11', '12', '13'];
            foreach ($xCodes as $xCode) {
                $yCode = (string)((int)$xCode + 10);
                $zCode = (string)((int)$xCode + 20);
                foreach ($entity['values'][$xCode] ?? [] as $index => $x) {
                    $y = $entity['values'][$yCode][$index] ?? null;
                    if (is_numeric($x) && is_numeric($y)) {
                        $z = $entity['values'][$zCode][$index] ?? 0;
                        $points[] = [(float)$x, (float)$y, is_numeric($z) ? (float)$z : 0.0];
                    }
                }
            }
            if ($type === 'LINE') {
                $primitives[] = [
                    'type' => 'line',
                    'start' => [
                        (float)($entity['values']['10'][0] ?? 0),
                        (float)($entity['values']['20'][0] ?? 0),
                    ],
                    'end' => [
                        (float)($entity['values']['11'][0] ?? 0),
                        (float)($entity['values']['21'][0] ?? 0),
                    ],
                ];
            } elseif ($type === 'CIRCLE') {
                $primitives[] = [
                    'type' => 'circle',
                    'center' => [
                        (float)($entity['values']['10'][0] ?? 0),
                        (float)($entity['values']['20'][0] ?? 0),
                    ],
                    'radius' => (float)($entity['values']['40'][0] ?? 0),
                ];
            }
        };

        foreach ($pairs as [$code, $value]) {
            if ($code === '0' && strtoupper($value) === 'SECTION') {
                continue;
            }
            if ($code === '2' && strtoupper($value) === 'ENTITIES') {
                $inEntities = true;
                continue;
            }
            if ($inEntities && $code === '0' && strtoupper($value) === 'ENDSEC') {
                $flush($current);
                $current = null;
                $inEntities = false;
                continue;
            }
            if (!$inEntities) {
                continue;
            }
            $upper = strtoupper($value);
            if ($code === '0' && in_array($upper, $entityTypes, true)) {
                $flush($current);
                $current = ['type' => $upper, 'values' => []];
                continue;
            }
            if ($current !== null) {
                $current['values'][$code][] = $value;
            }
        }
        $flush($current);
        ksort($counts);
        ksort($layers);

        return [
            'parser_mode' => 'php_ascii_dxf_v1',
            'entity_counts' => $counts,
            'layers' => $layers,
            'texts' => array_values(array_unique($texts)),
            'points' => $points,
            'primitives' => $primitives,
            'bbox' => Geometry::bbox($points),
            'warnings' => $counts === [] ? ['no_supported_entities'] : [],
        ];
    }

    private static function sourceEncoding(array $lines): string
    {
        $mapping = [
            'ANSI_949' => 'CP949',
            'ANSI_936' => 'GBK',
            'ANSI_950' => 'BIG-5',
            'ANSI_932' => 'SJIS-win',
            'ANSI_1252' => 'Windows-1252',
        ];
        $limit = min(count($lines) - 2, 2000);
        for ($index = 0; $index < $limit; $index++) {
            if (strtoupper(trim($lines[$index])) !== '$DWGCODEPAGE') {
                continue;
            }
            $codePage = strtoupper(trim($lines[$index + 2] ?? ''));
            return $mapping[$codePage] ?? 'Windows-1252';
        }
        return 'Windows-1252';
    }

    private static function utf8(string $value, string $sourceEncoding): string
    {
        if ($value === '' || mb_check_encoding($value, 'UTF-8')) {
            return $value;
        }
        return mb_convert_encoding($value, 'UTF-8', $sourceEncoding);
    }
}
