# Run integration tests for the rsync-s3 project (PowerShell version)

param(
    [switch]$KeepContainers,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Rsync.net S3 Gateway Integration Tests" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Change to project directory
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

try {
    # Build and start test containers
    Write-Host "▶ Building and starting test containers..." -ForegroundColor Yellow
    docker-compose -f docker-compose.test.yml build
    if ($LASTEXITCODE -ne 0) { throw "Build failed" }
    
    docker-compose -f docker-compose.test.yml up -d mock-rsync s3-gateway browser
    if ($LASTEXITCODE -ne 0) { throw "Failed to start containers" }

    # Wait for services to be ready
    Write-Host "▶ Waiting for services to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15

    # Check health
    Write-Host "▶ Checking service health..." -ForegroundColor Yellow
    docker-compose -f docker-compose.test.yml ps

    # Test S3 gateway is accessible
    Write-Host "▶ Testing S3 gateway connectivity..." -ForegroundColor Yellow
    $maxRetries = 5
    $retry = 0
    while ($retry -lt $maxRetries) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:9000" -Method Head -TimeoutSec 5 -ErrorAction SilentlyContinue
            Write-Host "  S3 Gateway responding" -ForegroundColor Green
            break
        } catch {
            $retry++
            if ($retry -lt $maxRetries) {
                Write-Host "  Waiting for S3 gateway... ($retry/$maxRetries)" -ForegroundColor Gray
                Start-Sleep -Seconds 3
            }
        }
    }

    # Test browser is accessible  
    Write-Host "▶ Testing browser connectivity..." -ForegroundColor Yellow
    $retry = 0
    while ($retry -lt $maxRetries) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8080/health" -TimeoutSec 5 -ErrorAction SilentlyContinue
            Write-Host "  Browser responding" -ForegroundColor Green
            break
        } catch {
            $retry++
            if ($retry -lt $maxRetries) {
                Write-Host "  Waiting for browser... ($retry/$maxRetries)" -ForegroundColor Gray
                Start-Sleep -Seconds 3
            }
        }
    }

    # Run tests
    Write-Host ""
    Write-Host "▶ Running integration tests..." -ForegroundColor Yellow
    
    if ($Verbose) {
        docker-compose -f docker-compose.test.yml run --rm test-runner pytest -v --tb=long integration/
    } else {
        docker-compose -f docker-compose.test.yml run --rm test-runner
    }
    
    $TestExitCode = $LASTEXITCODE

} finally {
    # Cleanup
    if (-not $KeepContainers) {
        Write-Host ""
        Write-Host "▶ Cleaning up..." -ForegroundColor Yellow
        docker-compose -f docker-compose.test.yml down -v
    } else {
        Write-Host ""
        Write-Host "▶ Keeping containers running (use docker-compose -f docker-compose.test.yml down to stop)" -ForegroundColor Yellow
    }
}

# Report
Write-Host ""
if ($TestExitCode -eq 0) {
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "  ✅ All tests passed!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
} else {
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "  ❌ Some tests failed" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
}

exit $TestExitCode
