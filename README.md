# Log Server

一个简单的 Python HTTP 记录服务，监听 `0.0.0.0:6565`（可配置），将所有请求内容与可重放命令记录到日志中，并用启动时读入的固定响应体进行回复。

## 特性
- 支持所有常见 HTTP 方法（GET/POST/PUT/PATCH/DELETE/OPTIONS）。
- 将请求的时间、客户端 IP、路径、头、正文（UTF-8 与 Base64）记录到文件。
- 自动生成可直接重放的 `curl`、`httpie` 命令及 `requests` Python 片段。
- 响应体仅在启动时从文件读取一次，运行期间保持不变。
- 响应 Content-Type 可自动猜测或手动指定。

## 运行要求
- Python 3.9+（仅使用标准库，无额外依赖）。

## 使用方法
1. 准备响应内容文件，例如 `response.txt`。
2. 启动服务：
   ```bash
   # 常规启动
   python3 server.py --response-file response.txt --log-file requests.log \
     --host 0.0.0.0 --port 6565

   # 启动前清空日志
   python3 server.py --response-file response.txt --log-file requests.log \
     --clear-log --host 0.0.0.0 --port 6565
   ```
   - `--response-file` 必填：服务器启动时读取并缓存的响应内容。
   - `--log-file` 可选：日志写入路径，默认 `requests.log`。
   - `--clear-log` 可选：启动前清空指定日志文件。
   - `--host` 可选：绑定地址，默认 `0.0.0.0`。
   - `--port` 可选：绑定端口，默认 `6565`。
   - `--content-type` 可选：手动设置响应的 Content-Type；未指定时按文件后缀猜测，文本类默认附加 `charset=utf-8`。

3. 发送请求测试：
   ```bash
   curl -i http://localhost:6565/hello -H 'X-Demo: test' -d 'ping'
   ```

## 日志内容示例（requests.log）
```
----- REQUEST START 2026-02-09T12:34:56 -----
client: 127.0.0.1
method: POST
path: /hello
url: http://localhost:6565/hello
headers:
  - Host: localhost:6565
  - User-Agent: curl/8.0.1
  - Accept: */*
  - X-Demo: test
  - Content-Length: 4
body:
  length: 4 bytes
  utf8: ping
  base64: cGluZw==
replay:
  curl: |
    curl -i -X POST -H 'Host: localhost:6565' -H 'User-Agent: curl/8.0.1' -H 'Accept: */*' -H 'X-Demo: test' -H 'Content-Length: 4' --data-raw 'ping' 'http://localhost:6565/hello'
  httpie: |
    http -v POST 'http://localhost:6565/hello' 'Host:localhost:6565' 'User-Agent:curl/8.0.1' 'Accept:*/*' 'X-Demo:test' 'Content-Length:4' --raw 'ping'
  python_requests: |
    import requests

    url = 'http://localhost:6565/hello'
    headers = {
        'Host': 'localhost:6565',
        'User-Agent': 'curl/8.0.1',
        'Accept': '*/*',
        'X-Demo': 'test',
        'Content-Length': '4',
    }
    data = 'ping'

    resp = requests.request('POST', url, headers=headers, data=data)
    print(resp.status_code)
    print(resp.text)
----- REQUEST END 2026-02-09T12:34:56 -----
```

## 关机与清理
- 按 `Ctrl+C` 停止服务。
- 日志文件默认会写在当前目录，可自行轮转或清理。

## 小贴士
- 如果响应文件是二进制（如图片、压缩包），建议使用 `--content-type` 手动指定正确类型。
- 日志中的 Base64 编码可用于还原原始请求体，防止乱码或不可打印字符丢失。
