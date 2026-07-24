<?php
declare(strict_types=1);

namespace CadAi\Parsers;

final class Geometry
{
    public static function bbox(array $points): ?array
    {
        if ($points === []) {
            return null;
        }
        $min = [INF, INF, INF];
        $max = [-INF, -INF, -INF];
        foreach ($points as $point) {
            for ($axis = 0; $axis < 3; $axis++) {
                $value = (float)($point[$axis] ?? 0.0);
                $min[$axis] = min($min[$axis], $value);
                $max[$axis] = max($max[$axis], $value);
            }
        }
        return [
            'min' => $min,
            'max' => $max,
            'extent' => [
                $max[0] - $min[0],
                $max[1] - $min[1],
                $max[2] - $min[2],
            ],
        ];
    }
}
