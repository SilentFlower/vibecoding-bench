# Synthetic byte-preservation reproduction
Create a dedicated temporary UTF-8 file with before_hex below. Call set_key(path, "COLOR", "new"). The original version reports (True, "COLOR", "new") and changes unrelated CRLF comments and the multi-line KEEP record to LF. The target line remains LF by existing design. Compare exact bytes and separately read KEEP with dotenv_values.

Before escaped: b'# untouched\r\nKEEP="first\r\nsecond"\r\nCOLOR=old\r\n'
Before hex: 2320756e746f75636865640d0a4b4545503d2266697273740d0a7365636f6e64220d0a434f4c4f523d6f6c640d0a
After original escaped: b'# untouched\nKEEP="first\nsecond"\nCOLOR=\'new\'\n'
After original hex: 2320756e746f75636865640a4b4545503d2266697273740a7365636f6e64220a434f4c4f523d276e6577270a
