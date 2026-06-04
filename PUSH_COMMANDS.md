# دستورهای Push به Git

اول یک ریپوی خالی روی GitHub/GitLab بساز (مثلاً اسمش `open_world_engine2` باشه).  
بعد **آدرس ریپو** رو جایگزین `آدرس-ریپوی-خودت` کن و این سه خط رو توی ترمینال بزن:

```bash
cd /root/agent/open_world_engine2
git remote add origin آدرس-ریپوی-خودت
git push -u origin master
```

**مثال با GitHub (با HTTPS):**
```bash
cd /root/agent/open_world_engine2
git remote add origin https://github.com/USERNAME/open_world_engine2.git
git push -u origin master
```

**مثال با GitHub (با SSH):**
```bash
cd /root/agent/open_world_engine2
git remote add origin git@github.com:USERNAME/open_world_engine2.git
git push -u origin master
```

اگر روی GitHub برنچ پیش‌فرض ریپو `main` است و خطا گرفتی، اول برنچ رو عوض کن بعد push کن:
```bash
git branch -M main
git push -u origin main
```
