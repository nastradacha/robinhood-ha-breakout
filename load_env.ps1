# Load environment variables from .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        Write-Host "$name = $value"
    }
}

# Verify critical variables are set
Write-Host "`nVerifying environment variables:"
Write-Host "ALPACA_API_KEY: $env:ALPACA_API_KEY"
Write-Host "ALPACA_SECRET_KEY: $env:ALPACA_SECRET_KEY" 
Write-Host "ALPACA_ENV: $env:ALPACA_ENV"
Write-Host "OPENAI_API_KEY: $($env:OPENAI_API_KEY.Substring(0,20))..."
Write-Host "SLACK_BOT_TOKEN: $($env:SLACK_BOT_TOKEN.Substring(0,20))..."
