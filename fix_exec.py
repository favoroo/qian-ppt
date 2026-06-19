import io

def fix_script_execution():
    with io.open('templates/editor.html', 'r', encoding='utf-8') as f:
        content = f.read()
        
    content = content.replace("newScript.appendChild(document.createTextNode(oldScript.innerHTML));", "newScript.text = oldScript.textContent;")
    
    with io.open('templates/editor.html', 'w', encoding='utf-8') as f:
        f.write(content)

fix_script_execution()
