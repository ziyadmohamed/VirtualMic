# دليل استخدام GitHub Actions لبناء الـ Driver

## الخطوات المطلوبة

### 1. إنشاء GitHub Repository

#### إذا لم يكن لديك حساب GitHub:
1. اذهب إلى https://github.com
2. اضغط "Sign Up"  
3. أنشئ حساب مجاني

#### إنشاء Repository جديد:
1. اذهب إلى https://github.com/new
2. Repository name: `VirtualMic` (أو أي اسم تريده)
3. اختر **Public** (مجاني ويتيح GitHub Actions)
4. **لا تضيف** README أو .gitignore (عندنا بالفعل)
5. اضغط "Create repository"

---

### 2. رفع المشروع لـ GitHub

افتح PowerShell في مجلد المشروع وقم بالتالي:

```powershell
cd d:\VirtualMic

# تهيئة Git repository
git init

# إضافة جميع الملفات
git add .

# عمل Commit
git commit -m "Initial commit - VirtualMic project with StMicDriver"

# ربط مع GitHub (استبدل YOUR_USERNAME باسمك)
git remote add origin https://github.com/YOUR_USERNAME/VirtualMic.git

# رفع الملفات
git branch -M main
git push -u origin main
```

**ملاحظة**: عند الـ push أول مرة، سيطلب منك تسجيل الدخول لـ GitHub.

---

### 3. تشغيل GitHub Actions

بمجرد رفع الكود، GitHub Actions سيبدأ تلقائياً!

#### مراقبة البناء:
1. اذهب إلى repository على GitHub
2. اضغط على تاب **Actions**
3. سترى workflow اسمه "Build StMicDriver" يعمل
4. اضغط عليه لرؤية التقدم

#### مدة البناء المتوقعة:
- ⏱️ تثبيت WDK: ~5-8 دقائق
- ⏱️ البناء: ~2-3 دقائق
- ⏱️ **الإجمالي**: ~10-15 دقيقة

---

### 4. تحميل الملفات المبنية

بعد انتهاء الـ workflow بنجاح:

1. في صفحة الـ workflow run، scroll لأسفل
2. ستجد قسم **Artifacts**
3. ستجد 3 ملفات ZIP:
   - `StMicDriver-Debug-x64.zip`
   - `StMicDriver-Release-x64.zip`  
   - `StMicDriver-Release-ZIP.zip` ⭐ **(الأفضل - استخدم هذا)**

4. حمل `StMicDriver-Release-ZIP.zip`
5. افك الضغط
6. ستجد بداخله:
   - `SimpleAudioSample.sys` - Driver file
   - `SimpleAudioSample.inf` - Installation file
   - `SimpleAudioSample.cat` - Catalog/signature

---

### 5. تثبيت الـ Driver

الآن عندك الملفات! اتبع الخطوات:

#### أ. تفعيل Test Signing (مرة واحدة فقط)

```powershell
# افتح PowerShell كـ Administrator
bcdedit /set TESTSIGNING ON
```

**⚠️ يجب عمل Restart للكومبيوتر!**

#### ب. تثبيت Driver

بعد الـ Restart:

```powershell
# افتح PowerShell كـ Administrator
cd "path\to\extracted\driver\files"

# استخدم PnPUtil (موجود في Windows)
pnputil /add-driver SimpleAudioSample.inf /install
```

**أو** استخدم DevCon:

```powershell
# حمل DevCon من:
# https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/devcon

devcon.exe install SimpleAudioSample.inf Root\SimpleAudioSample
```

#### ج. التحقق

1. افتح Device Manager (`devmgmt.msc`)
2. ابحث عن "Virtual Audio Device (WDM) - Simple Audio Sample"
3. يجب أن يظهر تحت "Sound, video and game controllers" بدون علامة تعجب

---

## استخدام Manual Trigger

إذا أردت إعادة البناء بدون عمل commit جديد:

1. اذهب لتاب **Actions** في GitHub
2. اضغط على "Build StMicDriver" من القائمة اليسرى
3. اضغط "Run workflow" (زر أزرق في اليمين)
4. اختر branch (main) واضغط "Run workflow"

---

## معالجة الأخطاء

### إذا فشل الـ Workflow:

1. اضغط على الـ workflow الفاشل
2. اضغط على الـ job "build"
3. افتح الخطوة اللي فشلت
4. اقرأ الخطأ

**الأخطاء الشائعة**:
- **WDK installation failed**: GitHub Actions ممكن يكون busy، جرب مرة تانية
- **Build failed**: ممكن يكون في مشكلة في الكود، تحقق من التفاصيل

### إذا لم تظهر Artifacts:

تأكد إن الـ workflow خلص بنجاح (علامة ✅ خضراء)

---

## الخطوات التالية

بعد تثبيت الـ Driver بنجاح:

### 1. تعديل Python Receiver
سنعدل `receiver.py` ليرسل الصوت للـ Driver عبر IOCTL

### 2. تعديل Android App
سنعدل التطبيق ليرسل عبر WiFi بدل Bluetooth

### 3. اختبار النظام كامل
Android → Network → Python → Driver → Windows Apps

---

## هل أنت جاهز؟

**الخطوة التالية**: 

قل لي إذا:
- ✅ **عملت repository على GitHub** - أرسل لي الرابط لو عايز أتأكد من الـ workflow
- ✅ **الـ workflow اشتغل بنجاح** - نكمل على Python و Android
- ❌ **واجهت مشكلة** - قولي إيه المشكلة وأنا هساعدك

**هل تريد مساعدة في أي خطوة من دول؟**
