<?php
declare(strict_types=1);

require dirname(__DIR__) . '/bootstrap.php';

use CadAi\Config;
use CadAi\HttpApp;

(new HttpApp(Config::fromEnvironment(dirname(__DIR__))))->handle();
