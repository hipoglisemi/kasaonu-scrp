import pexpect
import sys

print("Running reflutter...")
child = pexpect.spawn('/Users/hipoglisemi/Library/Python/3.9/bin/reflutter /Users/hipoglisemi/Desktop/oliz.apk', timeout=120)
child.expect(r'\[1/2\]\?')
child.sendline('1')
child.expect(r'BurpSuite IP:')
child.sendline('10.0.2.2')
child.expect(r'Please sign')
print("reFlutter completed!")
