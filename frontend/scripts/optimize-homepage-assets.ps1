param([ValidatePattern('^[a-z0-9-]+$')][string]$Batch = 'photoreal-v2')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$frontendPath = Split-Path $PSScriptRoot -Parent
$sourcePath = Join-Path $frontendPath "artifacts/$Batch-originals"
$briefs = Get-Content (Join-Path $PSScriptRoot "$Batch-image-briefs.json") -Encoding UTF8 -Raw | ConvertFrom-Json
$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq 'image/jpeg' } |
    Select-Object -First 1
$encoderParameters = [System.Drawing.Imaging.EncoderParameters]::new(1)
$encoderParameters.Param[0] = [System.Drawing.Imaging.EncoderParameter]::new(
    [System.Drawing.Imaging.Encoder]::Quality, [long]88
)

try {
    foreach ($brief in $briefs) {
        $folder = switch ($brief.folder) {
            'auth' { 'auth' }
            'workspace' { 'workspace' }
            default { 'home' }
        }
        $targetPath = Join-Path $frontendPath "public/images/$folder"
        New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
        $inputFile = Join-Path $sourcePath "$($brief.name).png"
        if (-not (Test-Path -LiteralPath $inputFile)) { throw "Missing generated image: $inputFile" }
        $image = [System.Drawing.Image]::FromFile($inputFile)
        try {
            $outputFile = Join-Path $targetPath "$($brief.name).jpg"
            $ratioParts = ($brief.ratio.Split(' ')[0]).Split(':')
            $aspectRatio = [double]$ratioParts[0] / [double]$ratioParts[1]
            $cropWidth = $image.Width
            $cropHeight = $image.Height
            if ($cropWidth / $cropHeight -gt $aspectRatio) {
                $cropWidth = [int][math]::Floor($cropHeight * $aspectRatio)
            } else {
                $cropHeight = [int][math]::Floor($cropWidth / $aspectRatio)
            }
            $bitmap = [System.Drawing.Bitmap]::new($cropWidth, $cropHeight)
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $destination = [System.Drawing.Rectangle]::new(0, 0, $cropWidth, $cropHeight)
                $graphics.DrawImage($image, $destination,
                    [int](($image.Width - $cropWidth) / 2), [int](($image.Height - $cropHeight) / 2),
                    $cropWidth, $cropHeight, [System.Drawing.GraphicsUnit]::Pixel)
                $bitmap.Save($outputFile, $codec, $encoderParameters)
            } finally {
                $graphics.Dispose()
                $bitmap.Dispose()
            }
            [pscustomobject]@{
                File = $brief.name
                Width = $cropWidth
                Height = $cropHeight
                KB = [math]::Round((Get-Item -LiteralPath $outputFile).Length / 1024)
            }
        } finally {
            $image.Dispose()
        }
    }
} finally {
    $encoderParameters.Dispose()
}
