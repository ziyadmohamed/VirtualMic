# دليل تثبيت أدوات بناء الـ Driver

## المشكلة الحالية

لبناء StMicDriver، نحتاج البرامج التالية ولكنها **غير مثبتة** على جهازك:

1. ❌ **Visual Studio** أو **Visual Studio Build Tools** (للـ C++ compiler)
2. ❌ **Windows Driver Kit (WDK)** (لملفات headers و libraries الخاصة بالـ drivers)

## الحلول المتاحة

### الخيار 1: تثبيت الأدوات المطلوبة (موصى به للتطوير)

#### الخطوة 1: تحميل Visual Studio Build Tools 2022

1. اذهب إلى: https://visualstudio.microsoft.com/downloads/
2. قم بتحميل **Build Tools for Visual Studio 2022**
3. قم بتشغيل الملف المحمل
4. اختر: **Desktop development with C++**
5. تأكد من تحديد:
   - ✅ MSVC v143 - VS 2022 C++ x64/x86 build tools
   - ✅ Windows SDK (أحدث إصدار)

**حجم التحميل**: ~5-7 GB

#### الخطوة 2: تحميل Windows Driver Kit (WDK)

1. اذهب إلى: https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk
2. قم بتحميل **WDK for Windows 11, version 22H2**
3. **مهم**: يجب تثبيت نفس إصدار Windows SDK الموجود في Build Tools

**حجم التحميل**: ~2-3 GB

#### الخطوة 3: بناء الـ Driver

بعد التثبيت، افتح **Developer Command Prompt for VS 2022**:

```cmd
cd d:\VirtualMic\StMicDriver
msbuild SimpleAudioSample.sln /p:Configuration=Debug /p:Platform=x64
```

الملفات المبنية ستكون في: `d:\VirtualMic\StMicDriver\x64\Debug\package\`

---

### الخيار 2: استخدام Driver جاهز (إذا كان موجود سابقاً)

إذا سبق لك بناء الـ Driver، يمكنك البحث عن الملفات:

```cmd
dir SimpleAudioSample.sys /s
```

إذا وجدت الملفات، يمكنك استخدامها مباشرة للتثبيت.

---

### الخيار 3: تحميل Driver مبني مسبقاً (إذا كان متوفراً)

إذا كان لديك نسخة مبنية من قبل على جهاز آخر أو من مصدر موثوق، يمكنك:

1. نسخ الملفات:
   - `SimpleAudioSample.sys`
   - `SimpleAudioSample.inf`
   - `SimpleAudioSample.cat` (للتوقيع)
2. وضعها في مجلد مثل `d:\VirtualMic\StMicDriver\prebuilt\`
3. الانتقال مباشرة للتثبيت

---

## الخطوات التالية بعد البناء

### 1. تفعيل Test Signing (مطلوب مرة واحدة)

```cmd
# يتطلب صلاحيات Administrator
bcdedit /set TESTSIGNING ON
```

**يجب عمل Restart للكومبيوتر بعد هذا الأمر**

### 2. تثبيت الـ Driver

```cmd
# تحميل DevCon من Windows SDK
# غالباً موجود في: C:\Program Files (x86)\Windows Kits\10\Tools\x64\devcon.exe

cd d:\VirtualMic\StMicDriver\x64\Debug\package
"C:\Program Files (x86)\Windows Kits\10\Tools\x64\devcon.exe" install SimpleAudioSample.inf Root\SimpleAudioSample
```

### 3. التحقق من التثبيت

1. افتح Device Manager: `devmgmt.msc`
2. ابحث عن "Virtual Audio Device (WDM) - Simple Audio Sample"
3. يجب أن يظهر تحت "Sound, video and game controllers"

---

## أسئلة شائعة

### هل يمكن استخدام Visual Studio Community بدلاً من Build Tools؟

نعم! Visual Studio Community مجاني ويتضمن كل الأدوات المطلوبة. عند التثبيت، اختر:
- Desktop development with C++
- ثم أثبت WDK بشكل منفصل

### ما هو الحجم الكلي للتحميل؟

- Build Tools + WDK: ~7-10 GB
- Visual Studio Community + WDK: ~15-20 GB

### هل يمكن بناء الـ Driver على جهاز آخر؟

نعم! يمكنك بناء الـ Driver على أي جهاز Windows يحتوي على Visual Studio + WDK، ثم نقل الملفات المبنية (`*.sys`, `*.inf`, `*.cat`) إلى جهازك الحالي.

### ماذا لو فشل التثبيت؟

تأكد من:
1. تفعيل Test Signing كما موضح أعلاه
2. تشغيل الأوامر بصلاحيات Administrator
3. إيقاف Driver Signature Enforcement مؤقتاً (عند الإقلاع: F8 > Disable driver signature enforcement)

---

## هل تريد المساعدة؟

إذا كنت تريد:
- ✅ **تثبيت الأدوات ثم بناء Driver**: أخبرني بعد التثبيت وسأساعدك في البناء
- ✅ **استخدام driver جاهز**: أخبرني وسأبحث عن نسخة مبنية في المشروع
- ✅ **استكمال بدون Driver**: يمكننا العمل على Android App و Python Receiver أولاً
