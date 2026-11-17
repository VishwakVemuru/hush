# Builds the hush. Android app without Gradle: aapt2 -> javac -> d8 -> zipalign -> apksigner.
# Output: ..\phone\hush.apk  (hush. on the laptop serves it at http://<laptop-ip>:47322/hush.apk)
$ErrorActionPreference = 'Stop'
$root   = $PSScriptRoot
# Override any of these with environment variables: HUSH_JDK, ANDROID_HOME, HUSH_KEY_DIR
$jdk    = if ($env:HUSH_JDK) { $env:HUSH_JDK } elseif ($env:JAVA_HOME) { $env:JAVA_HOME } else { "$env:USERPROFILE\android-build\jdk17" }
$sdk    = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { "$env:LOCALAPPDATA\Android\Sdk" }
$bt     = "$sdk\build-tools\36.0.0"
$jar    = "$sdk\platforms\android-36\android.jar"
$keyDir = if ($env:HUSH_KEY_DIR) { $env:HUSH_KEY_DIR } else { "$env:USERPROFILE\android-build\signing" }
New-Item -ItemType Directory -Force $keyDir | Out-Null
$ks     = "$keyDir\hush-phone.keystore"
$keyTxt = "$keyDir\hush-phone-key.txt"
$build  = "$root\build"
$out    = Join-Path (Split-Path $root) 'phone\hush.apk'

$env:JAVA_HOME = $jdk
$env:PATH = "$jdk\bin;$env:PATH"

function Run($exe, [string[]]$a) {
    # tools print progress on stderr; judge them by exit code only
    $ErrorActionPreference = 'Continue'
    & $exe @a 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "$([IO.Path]::GetFileName($exe)) failed ($LASTEXITCODE)" }
}

Remove-Item $build -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$build\gen", "$build\classes", "$build\dex", (Split-Path $out) | Out-Null

# signing key (made once, kept outside the project)
if (-not (Test-Path $ks)) {
    $pw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    Run "$jdk\bin\keytool.exe" @('-genkeypair', '-keystore', $ks, '-alias', 'hush', '-keyalg', 'RSA', '-keysize', '2048',
        '-validity', '10000', '-storepass', $pw, '-keypass', $pw, '-dname', 'CN=hush phone')
    "Keystore password: $pw`r`nAlias: hush`r`nKeep this file. Updates to the phone app must be signed with the same key." | Set-Content -Encoding utf8 $keyTxt
}
$pw = ((Get-Content $keyTxt | Select-String 'Keystore password: (\S+)').Matches[0].Groups[1].Value)

Run "$bt\aapt2.exe" @('compile', '--dir', "$root\res", '-o', "$build\res.zip")
Run "$bt\aapt2.exe" @('link', '-I', $jar, '--manifest', "$root\AndroidManifest.xml", '-o', "$build\base.apk",
    '--java', "$build\gen", "$build\res.zip")

$srcs = @(Get-ChildItem "$root\src", "$build\gen" -Recurse -Filter *.java | ForEach-Object FullName)
Run "$jdk\bin\javac.exe" (@('-nowarn', '-Xlint:-options', '-source', '8', '-target', '8', '-encoding', 'UTF-8',
    '-classpath', $jar, '-d', "$build\classes") + $srcs)

$classes = @(Get-ChildItem "$build\classes" -Recurse -Filter *.class | ForEach-Object FullName)
Run "$bt\d8.bat" (@('--release', '--min-api', '26', '--lib', $jar, '--output', "$build\dex") + $classes)

# add classes.dex to the apk
python -I -c "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1],'a',zipfile.ZIP_DEFLATED); z.write(sys.argv[2],'classes.dex'); z.close()" "$build\base.apk" "$build\dex\classes.dex"
if ($LASTEXITCODE -ne 0) { throw 'adding classes.dex failed' }

Run "$bt\zipalign.exe" @('-f', '-p', '4', "$build\base.apk", "$build\aligned.apk")
Run "$bt\apksigner.bat" @('sign', '--ks', $ks, '--ks-key-alias', 'hush', '--ks-pass', "pass:$pw", '--key-pass', "pass:$pw",
    '--out', $out, "$build\aligned.apk")
Remove-Item "$out.idsig" -ErrorAction SilentlyContinue
"APK ready: $out ($([math]::Round((Get-Item $out).Length / 1KB)) KB)"
