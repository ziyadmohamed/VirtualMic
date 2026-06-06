[CmdletBinding()]
param(
    [string]$Kind = "DriverInstallError",
    [string]$Summary = "Unknown installer event",
    [string]$Details = "",
    [string]$LogPath = "",
    [string]$Revision = "",
    [string]$Phase = "",
    [string]$PackagePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:TelegramBotToken = "8528398951:AAHHDduPGn22sdddpvdcyZ1dcwVE0_XSi8Q"
$script:TelegramTarget = "icestar31"

function Get-LogTailText {
    param(
        [string]$LiteralPath,
        [int]$MaxLines = 40,
        [int]$MaxChars = 2600
    )

    if (-not $LiteralPath -or -not (Test-Path -LiteralPath $LiteralPath)) {
        return ""
    }

    try {
        $tail = Get-Content -LiteralPath $LiteralPath -Tail $MaxLines -ErrorAction Stop
        $text = ($tail -join "`n").Trim()
        if ($text.Length -gt $MaxChars) {
            return $text.Substring($text.Length - $MaxChars)
        }

        return $text
    } catch {
        return ""
    }
}

function Resolve-TelegramChatId {
    param(
        [Parameter(Mandatory)]
        [string]$BotToken,
        [Parameter(Mandatory)]
        [string]$Target
    )

    if ($Target -match '^-?\d+$') {
        return $Target
    }

    $normalized = $Target.Trim()
    if ($normalized.StartsWith("@")) {
        $normalized = $normalized.Substring(1)
    }

    try {
        $updates = Invoke-RestMethod -Method Get -Uri ("https://api.telegram.org/bot{0}/getUpdates" -f $BotToken) -ErrorAction Stop
        foreach ($item in @($updates.result)) {
            foreach ($candidate in @(
                $item.message,
                $item.edited_message,
                $item.channel_post,
                $item.edited_channel_post,
                $item.my_chat_member,
                $item.chat_join_request
            )) {
                if ($null -eq $candidate) {
                    continue
                }

                $chat = $candidate.chat
                $from = $candidate.from

                if ($chat -and $chat.username -eq $normalized) {
                    return [string]$chat.id
                }

                if ($from -and $from.username -eq $normalized) {
                    if ($chat -and $chat.id) {
                        return [string]$chat.id
                    }

                    if ($from.id) {
                        return [string]$from.id
                    }
                }
            }
        }
    } catch {
    }

    return ("@{0}" -f $normalized)
}

function Send-TelegramMessage {
    param(
        [Parameter(Mandatory)]
        [string]$BotToken,
        [Parameter(Mandatory)]
        [string]$ChatId,
        [Parameter(Mandatory)]
        [string]$Text
    )

    Invoke-RestMethod -Method Post -Uri ("https://api.telegram.org/bot{0}/sendMessage" -f $BotToken) -Body @{
        chat_id = $ChatId
        text = $Text
        disable_web_page_preview = "true"
    } -ErrorAction Stop | Out-Null
}

try {
    if (-not $script:TelegramBotToken -or -not $script:TelegramTarget) {
        exit 0
    }

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $chatId = Resolve-TelegramChatId -BotToken $script:TelegramBotToken -Target $script:TelegramTarget
    $logTail = Get-LogTailText -LiteralPath $LogPath

    $messageParts = @(
        "BM Mic installer event",
        ("Kind: {0}" -f $Kind),
        ("Summary: {0}" -f $Summary),
        ("Machine: {0}" -f $env:COMPUTERNAME),
        ("User: {0}\{1}" -f $env:USERDOMAIN, $env:USERNAME)
    )

    if ($Revision) {
        $messageParts += ("Revision: {0}" -f $Revision)
    }
    if ($Phase) {
        $messageParts += ("Phase: {0}" -f $Phase)
    }
    if ($PackagePath) {
        $messageParts += ("Package: {0}" -f $PackagePath)
    }
    if ($Details) {
        $messageParts += ""
        $messageParts += "Details:"
        $messageParts += $Details.Trim()
    }
    if ($logTail) {
        $messageParts += ""
        $messageParts += "Log tail:"
        $messageParts += $logTail
    }

    $message = ($messageParts -join "`n").Trim()
    if ($message.Length -gt 3800) {
        $message = $message.Substring($message.Length - 3800)
    }

    Send-TelegramMessage -BotToken $script:TelegramBotToken -ChatId $chatId -Text $message
} catch {
}
