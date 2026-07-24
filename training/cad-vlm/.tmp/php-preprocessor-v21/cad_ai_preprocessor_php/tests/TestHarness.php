<?php
declare(strict_types=1);

namespace CadAi\Tests;

final class TestHarness
{
    private array $results = [];

    public function run(string $name, callable $test): void
    {
        $started = hrtime(true);
        try {
            $test();
            $this->results[] = [
                'name' => $name,
                'successful' => true,
                'duration_ms' => round((hrtime(true) - $started) / 1_000_000, 3),
                'error' => null,
            ];
        } catch (\Throwable $exception) {
            $this->results[] = [
                'name' => $name,
                'successful' => false,
                'duration_ms' => round((hrtime(true) - $started) / 1_000_000, 3),
                'error' => $exception::class . ': ' . $exception->getMessage(),
            ];
        }
    }

    public function assertTrue(bool $condition, string $message): void
    {
        if (!$condition) {
            throw new \RuntimeException($message);
        }
    }

    public function assertSame(mixed $expected, mixed $actual, string $message): void
    {
        if ($expected !== $actual) {
            throw new \RuntimeException(
                $message . ' expected=' . var_export($expected, true)
                . ' actual=' . var_export($actual, true)
            );
        }
    }

    public function assertThrows(string $exceptionClass, callable $operation, string $message): void
    {
        try {
            $operation();
        } catch (\Throwable $exception) {
            if ($exception instanceof $exceptionClass) {
                return;
            }
            throw new \RuntimeException($message . ' unexpected=' . $exception::class);
        }
        throw new \RuntimeException($message . ' no exception');
    }

    public function results(): array
    {
        return $this->results;
    }

    public function successful(): bool
    {
        return !in_array(false, array_column($this->results, 'successful'), true);
    }
}
