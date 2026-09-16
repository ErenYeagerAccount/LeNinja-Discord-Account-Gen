# 🌟 LeNinja - AI-Powered CAPTCHA Solver

```
+---------------------------------------------------------------+
|                                                               |
|                            LeNinja                            |
|                  Account automation console                   |
|                                                               |
+---------------------------------------------------------------+
```

## ✨ Features

- 🎨 **Vibrant UI** - Beautiful gradient design with purple, pink, cyan, and gold colors
- 🤖 **AI-Powered** - Advanced machine learning algorithms for CAPTCHA solving
- 🚀 **Fast & Efficient** - Solves CAPTCHAs in seconds
- 🔒 **Data handling** - Uses third-party services; account passwords and tokens are stored locally in plaintext.
- 🌐 **Universal** - Supports reCAPTCHA, hCAPTCHA, FunCaptcha, and more

## 🎯 Supported CAPTCHA Types

- ✅ reCAPTCHA v2 & v3
- ✅ hCAPTCHA
- ✅ FunCaptcha (Arkose Labs)
- ✅ Cloudflare Turnstile
- ✅ AWS CAPTCHA
- ✅ GeeTest
- ✅ Text CAPTCHA
- ✅ PerimeterX
- ✅ Lemin CAPTCHA

## 🚀 Quick Start

1. **Install Requirements**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API Key**
   - Add your API key to `config/nopecha.txt`
   - Configure settings in `config/config.yaml`

3. **Run the Tool**
   ```bash
   python main.py
   ```

## 🎨 UI Preview

The extension features a stunning gradient design with:
- 💜 Purple to Pink gradients
- 🔵 Cyan accent colors
- 💛 Gold highlights
- ✨ Animated rainbow borders
- 🌈 Glowing effects on interactive elements

## ⚙️ Configuration

Edit `config/config.yaml` to customize:
- VPN settings
- Email provider (Cybertemp, Hotmail, Zeus-X, Afham, DuckMail, CrowMail)
- API keys
- Cooldown timers

### Logging

Runtime logs are written to `logs/leninja.log` with automatic rotation. Set
`LENINJA_LOG_LEVEL=DEBUG` before starting the program to enable debug output;
supported levels are `DEBUG`, `INFO`, `WARNING`, and `ERROR`.

## 📦 Extension Installation

The LeNinja browser extension is automatically downloaded on first run. Use **DuckDuckGo Browser**. Chrome, Brave, Edge, Vivaldi, and Ungoogled Chromium are not launched in auto mode because Discord register stays blank.

## 🔧 Advanced Features

- **Proxy Support** - Rotate IPs with VPN integration
- **Multi-Account Generation** - Create unlimited accounts
- **Smart Cooldown** - Intelligent rate limiting

## 📝 License

This project is for educational purposes only. Use responsibly and in accordance with the terms of service of the websites you interact with.

## 🌟 Credits

LeNinja is the project branding. The bundled third-party CAPTCHA extension is provided by NopeCHA; its provider identifiers and integration paths retain their original names.

---

**Made with 💜 by the LeNinja Team**

## Security and review notes

- Keep API keys and generated credentials private. Remove credentials before sharing an initialized project: runtime setup can write keys into the extension files.
- Default provider credentials have been removed from the distributable source. Rotate previously exposed keys with their providers.
- The final summary counts valid and locked results separately. These are observations at the time of checking, not guarantees of future token validity.
- Git exclusions reduce accidental commits; they do not encrypt files, protect ZIP archives, or remove previously tracked secrets.

### Remaining issues found during review

- The bundled extension is heavily obfuscated and has broad browser permissions.

Runtime setup, mailbox validation, output writes, and VPN failure handling were updated in a later pass.
