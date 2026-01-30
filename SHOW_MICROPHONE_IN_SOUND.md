# خطوات إظهار Virtual Microphone في Sound Settings

## الوضع الحالي
✅ Driver ظهر في Device Manager بدون أخطاء  
❓ لسه مش ظاهر في Sound Settings كـ Microphone

---

## الحل: إظهار Disabled/Disconnected Devices

### افتح Sound Control Panel

**الطريقة 1** (PowerShell):
```powershell
control mmsys.cpl
```

**الطريقة 2** (GUI):
- كليك يمين على أيقونة الصوت في Taskbar
- **Sound settings**
- scroll لأسفل → **More sound settings** أو **Sound Control Panel**

---

### في تاب "Recording"

1. **كليك يمين** في المساحة الفاضية (المكان الفاضي بين الأجهزة)
2. ✅ **اختر "Show Disabled Devices"**
3. ✅ **اختر "Show Disconnected Devices"**

---

## السيناريوهات المحتملة

### السيناريو أ: Device ظهر ✅
- Device اسمه: **"Microphone (Virtual Audio Device)"** أو **"Microphone Array"**
- لو عليه علامة ⬇️ (Disabled):
  - كليك يمين → **Enable**
- بعدها:
  - كليك يمين → **Set as Default Device**
  - كليك يمين → **Set as Default Communication Device**

**تم! ✅ Virtual Microphone شغال**

---

### السيناريو ب: Device مش ظاهر ❌

**السبب**: Audio subsystem محتاج restart

**الحل 1 - Restart Audio Services**:
```powershell
# PowerShell كـ Administrator
net stop audiosrv
net start audiosrv
```

**الحل 2 - Restart الكومبيوتر** (أضمن):
```powershell
shutdown /r /t 0
```

---

### السيناريو ج: Device ظاهر بس عليه ❌ حمراء

**السبب**: Driver مش شغال صح

**الحل**:
1. افتح Device Manager (`devmgmt.msc`)
2. ابحث عن **Virtual Audio Device**
3. كليك يمين → **Properties**
4. شوف "Device status" - إيه الخطأ؟
5. لو **Code 10** أو **Code 52**:
   ```powershell
   # PowerShell كـ Admin
   bcdedit /set testsigning on
   shutdown /r /t 0
   ```

---

## بعد ما يظهر وتعمله Enable

**جرّب الميكروفون**:
1. في Sound Control Panel → تاب Recording
2. اتكلم أو شغل صوت
3. المفروض الـ green bars تتحرك جنب الميكروفون
4. لو مش بتتحرك → **معناه Driver محتاج audio data من Python receiver**

---

## الخطوة التالية

بعد ما Virtual Microphone يظهر ويكون Enabled:
- ✅ نبدأ نشتغل على **Python receiver** عشان يبعت صوت للـ driver
- ✅ نعدل **Android app** للـ WiFi streaming

**قولي وصلت لأي مرحلة!** 🎯
