任务1：进一步学习并理解项目，将一下信息补全到#basePrompt.md中：1、项目名称：智能数据瞭望与智能问数系统2、项目背景：通过B/S技术实现一款智能数据采集到深度采集再到数据分析与问数的综合业务系统，以大模型驱动整个业务系统的运行，是一款轻量级的智能（体）应用。3、技术栈：python(conda envs qq_monitors)+sqlite3+websocket+sse+tornado+tornadoTemplate

任务 2：进一步学习并理解项目，将以下信息补充到 #basePrompt.md 中：1、dist 目录下，放置了三个包，用于后台管理侧开发时使用，其：—zui-3.0.0.zip：ZUI 3 是一个开源 UI 组件库，提供了大量实用组件，支持最大限度的定制，不依赖任何其他 JS 框架，可以在任何 Web 应用中通过原生的方式使用。（开发帮助：https://openzui.com/guide/start/intro.html，组件库帮助：https://openzui.com/lib/basic/core/css-component.html），需要解压 app/static 目录下。—bootstrap-5.3.8-dist.zip ：Bootstrap 5.3.8 是一个基于 Bootstrap 5.3.8 版本的 UI 组件库，提供了大量实用组件，支持最大限度的定制，不依赖任何其他 JS 框架，可以在任何 Web 应用中通过原生的方式使用。（开发帮助：https://getbootstrap.com/docs/5.3/getting-started/introduction/ ），需要解压app/static 目录下。—fontawesome-free-6.4.0-web.zip ：FontAwesome Awesome 6.4.0 是一个基于 FontAwesome Awesome 6.4.0 版本的图标库，提供了大量图标，支持自定义图标，可以在任何 Web 应用中通过原生的方式使用。（开发帮助：https://fontawesome.com/docs/v6.4.0/getting-started/using-free ），需要解压 app/static 目录下。

任务 3：进一步学习并理解项目，将以下信息补充到 #basePrompt.md 中：1、设计风格：自适应浏览器用户区设计、响应式布局、沉浸式操作。2、所有开发将基于上下文工程提示完成，所有操作需要同步记录和维护以下几个文件：docs/basePrompt.md (项目基础提示，AI 维护)docs/codingPrompt.md (项目编码提示，人类和AI共同维护，你适量干预，从而优化项目)docs/requirementPrompt.md (项目需求提示，AI 维护)

任务 4：开始编码实现业务功能模块：1、完成后台 - 管理侧功能模块的开发：后台登录：采用响应式设计、沉浸式操作、自适应设计，界面风格以企业化管理软件风格为主，简约专业（后台主要是 admin 专员使用，默认用户名密码为：admin/admin888），界面参考上传的 UI 效果图风格开发，登录面板需要居中屏幕中间位置。后台主页：登录后进入后台主页，后期根据需求添加功能模块，本次任务不开发。后台管理：采用 zui 组件实现传统后台管理系统布局：上（LOGO / 系统名称 / 用户信息 /）左（菜单区）右（工作区）布局，菜单需要有图标 + 文字风格设计。2、开发限制：严格遵循 #basePrompt.md 中的设计风格和组件库使用要求。所有开发操作需要同步记录和维护以下几个文件：docs/basePrompt.md (项目基础提示，AI 维护)docs/codingPrompt.md (项目编码提示，人类维护，你不用干预)docs/requirementPrompt.md (项目需求提示，AI 维护)

任务 4.1: 发现问题，检查代码，修复问题:将后续开发所需要涉及到的表、数据自行设计写入数据库，包括表的创建、维护等操作，这个需要写入 docs/requirementPrompt.md 和 docs/basePrompt.md 中。

任务 5：开始编码实现业务功能模块：1、完成后台 - 管理侧功能模块的开发：角色管理：系统分为普通用户、管理用户两大类，普通用户可以通过用户侧测试获得访问前台用户侧的功能权限。管理用户可以通过后台添加用户获得管理侧权限，管理用户类默认超级管理员（admin），该角色不允许删除和修改，可以新增角色 / 删除 / 查看 / 修改 / 分页（20 条 / 页）/ 搜索（模糊查询），需要联动功能管理，实现角色动态设置功能（二级联动的方式实现）用户管理：实现用户新增 / 删除（admin 不允许删除）/ 修改 / 查看 / 分页 / 搜索功能管理：将菜单功能管理化，实现功能的新增 / 删除 / 修改 / 查看 / 分页 / 搜索2、开发限制：严格遵循 #basePrompt.md 中的设计风格和组件库使用要求。确保所有页面的布局、样式、交互等符合设计风格且统一、规范、一致。要求写主维护 Prompt。所有开发操作需要同步记录和维护以下几个文件，维护更新为每个大任务完成后，新的大任务开发前更新维护：docs/basePrompt.md (项目基础提示，AI 维护)docs/codingPrompt.md (项目编码提示，人类维护，你不用干预)docs/requirementPrompt.md (项目需求提示，AI 维护)

任务 5.1: 发现问题，检查代码，修复问题:发现所有新增 / 修改未实现弹窗面板操作，需要优化。删除 / 保存 / 更新需要有提示，确认后操作。

任务 6：任务 5：开始编码实现业务功能模块：1、完成后台 - 管理侧功能模块的开发：模型引擎：-- 实现以橱窗列表展示及独立的页面风格，页面风格以大模型科技感、炫酷风格为主，区别现在的 ZUI 风格。-- 实现动态新增 / 删除 / 修改 / 查询模型引擎。-- 支持可视化配置满足 OPENAI-API 范式的模型服务配置与调用。-- 支持统计 Token (可视化)。-- 支持分页 - 行 / 三列。6 条 / 页。-- 支持对模型进行单独的对话测试。-- 支持设置模型：默认 / 模型类型（文字 / 多模态 / 视觉 / 向量）/ 模型参数（如温度、最大长度等）/ 系统提示（system_prompt）。-- 支持 SSE 流式响应（开关化），支持模型 Think 开关化-- 如要设置为默认模型，系统后续调用模型服务时，优先调用默认模型。2、以下为 openai 代码示例：

    from openai import OpenAI
    import os
    
    client = OpenAI(
        # 如果没有配置环境变量，请用阿里云百炼API Key替换：api_key="sk-"
        api_key=os.getenv("sk-62736c5576ad4172861f1f618459075b"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    
    messages = [{"role": "user", "content": "你是谁"}]
    completion = client.chat.completions.create(
        model="qwen3.6-plus",  # 您可以按需更换为其它深度思考模型
        messages=messages,
        extra_body={"enable_thinking": True},
        stream=True
    )
    is_answering = False  # 是否进入回复阶段
    print("\n" + "=" * 20 + "思考过程" + "=" * 20)
    for chunk in completion:
        delta = chunk.choices[0].delta
        if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
            if not is_answering:
                print(delta.reasoning_content, end="", flush=True)
        if hasattr(delta, "content") and delta.content:
            if not is_answering:
                print("\n" + "=" * 20 + "完整回复" + "=" * 20)
                is_answering = True
            print(delta.content, end="", flush=True)

3、开发限制：严格遵循 #basePrompt.md 中的设计风格和组件库使用要求。确保所有页面的布局、样式、交互等符合设计风格且统一、规范、一致。要求写主维护 Prompt。所有开发操作需要同步记录和维护以下几个文件，维护更新为每个大任务完成后，新的大任务开发前更新维护：docs/basePrompt.md (项目基础提示，AI 维护)docs/codingPrompt.md (项目编码提示，人类维护，你不用干预)docs/requirementPrompt.md (项目需求提示，AI 维护)

任务 7：开始编码实现业务功能模块：1、完成后台 - 管理侧功能模块的开发：瞭望采集：通过大模型 + AI 实现智能数据采集，支持新增瞭望数据源管理及采集功能，以下为具体要求：-- 瞭望源管理：一个可动态可视化管理采集规则的功能模块，支持新增 / 修改 / 删除 / 查询等操作。该功能模块可以管理：采集 URL，采集 URL 对应的 RequestHeader 等信息，我将给你提供一个采集源的包数据，供你分析实现该管理功能。以下为以下为百度新闻的更新的请求 URL 和 RequestHeaders:https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word=西华师范大学https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word={关键词}https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word=西华师范大学&pn=10https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word={关键词}&pn={分页步进：默认0=第一页，10=第二页，20=第三页……}

Request Headers的包数据(raw)：

    GET /s?wd=%E8%A5%BF%E5%8D%8E%E5%B8%88%E8%8C%83%E5%A4%A7%E5%AD%A6&tn=15007414_23_dg&ie=utf-8 HTTP/1.1
    Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7
    Accept-Encoding: gzip, deflate, br, zstd
    Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6
    Cache-Control: max-age=0
    Connection: keep-alive
    Cookie: MAWEBCUID=web_zPFMIPmwMtvAcIfNWNUpySAysTgQaiWZkAGxLaaobpZTKoEuQa; BAIDUID=76CD34EFBF9E36837E234CF5CC42F6D0:FG=1; sugstore=0; PSTM=1766289966; BIDUPSID=7E4ACD90B317CB0E63245D8AAE790CEF; BD_UPN=12314753; BDUSS=2t6b09MVmpoekVNcHNnS0kxfmxwUkpOUk1QYnIzM0JUSVhaeTIwN1o5LUZuRlZxSVFBQUFBJCQAAAAAAQAAAAEAAADuteqXsK7Jz87SsrvKx7Tty68AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIUPLmqFDy5qY; BDUSS_BFESS=2t6b09MVmpoekVNcHNnS0kxfmxwUkpOUk1QYnIzM0JUSVhaeTIwN1o5LUZuRlZxSVFBQUFBJCQAAAAAAQAAAAEAAADuteqXsK7Jz87SsrvKx7Tty68AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIUPLmqFDy5qY; BAIDUID_BFESS=76CD34EFBF9E36837E234CF5CC42F6D0:FG=1; ZFY=ayM3mg0vIwvRLsnrnlxc6q4b4pSHIfDylN2e9ZY7S9E:C; H_WISE_SIDS_BFESS=63143_67721_67862_69000_69295_69961_70117_70801_70807_70546_70506_70904_70966_70996_71035_71041_71054_71068_71080_71094_71103; __bid_n=19ece7111ae8048dedb937; minjie_card=1; H_PS_PSSID=63143_67721_67862_69000_69295_70117_70801_70807_70506_70966_70996_71035_71041_71054_71068_71080_71094_71103_71134_71139; BA_HECTOR=00al8005agag058l8ga0al0k2h2k001l34h3i28; ab_sr=1.0.1_YWZjNGVlNjkwYzk0ZWY5MjI3ZTAzYWExNzFjMjU4NzBiYjRhM2I3ZjZiM2JjYjVmNTIyMDBhM2VmM2RmMzcxZDA5ZTE0MWY0YWE5MmIwNWZjODljMTkxOTE2ZmYxNzgzOTk2Y2M5OGExNjMwODBmNTVmN2RlNDE3NTA4ODgwYTNhZjJlM2I1YzgwNTY3NWY5Y2E3MmFhOWUyNWQ1YTZjNGJmMzQwZmIzM2Q1OWY2MjY5ZmU1MTZlYWEzNjQ5ZGEzMWE0MWIxODU5ODhiOGIxODQ0MGZkODNjMTg1OTg1ODY=; BDRCVFR[uPX25oyLwh6]=mk3SLVN4HKm; delPer=0; H_WISE_SIDS=63143_67721_67862_69000_69295_70117_70801_70807_70506_70966_70996_71035_71041_71054_71068_71080_71094_71103_71134_71139; COOKIE_SESSION=1818_0_4_0_8_17_1_0_4_3_0_1_84273_0_3_0_1781681036_0_1781681033%7C9%231820848_16_1781422019%7C9; PSINO=5; SMARTINPUT=%5Bobject%20Object%5D; H_PS_645EC=2b64C9%2BwVh%2Fbt1IPwk8ri9ZAaAmxKYMyiDbC%2FKb81NrpS%2BFy9R0ptOF7qiAmhahYAl%2FkZOc
    Host: www.baidu.com
    Sec-Fetch-Dest: document
    Sec-Fetch-Mode: navigate
    Sec-Fetch-Site: cross-site
    Sec-Fetch-User: ?1
    Upgrade-Insecure-Requests: 1
    User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0
    sec-ch-ua: "Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"
    sec-ch-ua-mobile: ?0
    sec-ch-ua-platform: "Windows"

-- 瞭望采集：---- 开发一个类似搜索引擎的界面，主输入框下方提供采集源的动态选择功能（开关样式），该界面要求独立风格不与 ZUI 风格同步，炫酷、好看，用户交互体验简单，在采集源的选择面板下，提供参考配置面板（一次有效的采集数量和页数（与 Url 中的参数同步）），在参数面板的下方，实时呈现采集到列表 (采用橱窗模式，1 行 3 列)，列表支持多选 / 全选，最终可以将选中的数据保存到数据库对应表中。为下一步深度采集做数据储备。



任务 8：继续编码实现业务功能模块：
1、完成后台 - 管理侧功能模块的开发：
数据仓库模块：以列表显示通过瞭望采集到数据，20 / 页，支持删除 / 批量删除 / 查询 / AI 深度采集（后续单独任务开发实现：AI 深度采集分为单挑采集和多条批量采集）
2、开发限制：
严格遵循 #basePrompt.md 中的设计风格和组件库使用要求。
确保所有页面的布局、样式、交互等符合设计风格且统一、规范、一致。要求写主维护 Prompt。
所有开发操作需要同步记录和维护以下几个文件，维护更新为每个大任务完成后，新的大任务开发前更新维护：
docs/basePrompt.md (项目基础提示，AI 维护)
docs/codingPrompt.md (项目编码提示，人类维护，你不用干预)
docs/requirementPrompt.md (项目需求提示，AI 维护)



任务 9：继续编码实现业务功能模块：
1、完成后台 - 管理侧功能模块的开发：
深度采集：通过技术手段对采集到数据源进行深度解析，并获得详细的内容，同时需要将详细内容存储到深度采集对应的表中，还需要与数据仓库中的源进行关联，可以在数据仓库中显示是否深度采集状态，只有采集过的数据，可以查看深度采集到的详细内容。
-- 深度采集支持单条或多条数据采集，深度采集过程需要有过程提示，需要有采集日志，对结果有简单的统计分析。
-- 深度采集的技术栈：通过模型引擎中的默认大模型服务 + crawl4ai 共同完成。
-- 深度采集完成后，需要在数据仓库列表中标注深度采集状态。
2、开发限制：
严格遵循 #basePrompt.md 中的设计风格和组件库使用要求。
确保所有页面的布局、样式、交互等符合设计风格且统一、规范、一致。要求写主维护 Prompt。
所有开发操作需要同步记录和维护以下几个文件，维护更新为每个大任务完成后，新的大任务开发前更新维护：
docs/basePrompt.md (项目基础提示，AI 维护)
docs/codingPrompt.md (项目编码提示，人类维护，你不用干预)
docs/requirementPrompt.md (项目需求提示，AI 维护)




任务 10：开台编码实现前台用户侧功能模块：
1、完成前台用户侧功能模块的开发：
用户登录：手用后端 - 管理侧登录模块，实现前端用户侧普通用户的登录功能，与管理和户共用一套健全逻辑，但是需要区分角色（普通用户）
用户注册：开放允许注册为普通用户
AI 问数：界面风格采用与 chatGPT / 豆包风格类似的可以与 AI 对话界面效果，需要实现以下功能：
-- 与 AI 对话，通过 AI 调用技能工具 SQL 实现与 SQLite 库中相关数据表进行数据问数。（如涉及 SQL 语句，不允许 AI 显示具体的 SQL 语句内容）
-- 需要建立意图识别，分析用户的问题是问数据库中的表数据还是问其他的问题（问天气 / 问音乐等），这里涉及到不同技能工具的调用和调度。
-- 预留 @xxx 功能与后台数字员工对话的能力 (后续单独任务实现)
-- 响应数据采用流式响应（SSE）
-- 左侧需要实现模型服务切换（模型服务来自后台模型引擎中可用的模型，默认使用默认模型）
-- 左侧需要实现历史对话记录，点击可以查看和回放即使对话数据。
-- 对话渲染采用 markdown 格式渲染结果。