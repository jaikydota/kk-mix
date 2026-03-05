

1. 新增一个视频配音的tab
2. 视频配音tab 的代码放在新的文件  speech_tab.py 中，然后kk.py 再import speech_tab 加载代码逻辑
3. 视频配音 UI 包括： 输入文件夹选择框，配音文案文件夹选择框，输出文件夹选择框，以及日志
4. 输入文件夹选择框 跟 music_replace.py 中的文件夹选择类似， 文件夹存放的是要配音的视频文件
5. 输入文件夹选择框 跟 music_replace.py 中的文件夹选择类似， 文件夹存放的是配音的文案文件。
6. 配音的视频文件和文案文件顺序一致。如果两边大小不同，则报错
7. 配音的 tts 调用 mcp 的 tts 接口实现。接口文档参见 docs/guide/mcp_client.md 文件