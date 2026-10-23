"""Chinese explanations grounded in the metadata and README already read."""
import re

KINDS = {
    'api-service': ('在线 API 接入', '这个仓库提供在线 API 的接入说明和示例，需申请服务方的 Key，再在客户端配置 API 地址和模型；未发现可独立部署的服务入口。'),
    'examples': ('示例与教程', '这是供你学习和改造的代码示例集合。先选一个案例，再按案例说明使用。'),
    'awesome': ('资源清单', '这是整理好的资源目录，可以按主题寻找工具、教程和其他项目。'),
    'prompts': ('提示词合集', '这是可参考和改写的提示词集合，主要通过阅读、复制和调整内容来使用。'),
    'dataset': ('数据集', '这是供程序读取和分析的数据资源，需要先核对数据格式和使用说明。'),
    'library': ('开发库', '这是供开发者集成到代码中的库，使用前需要查看接口和示例。'),
    'cli': ('命令行工具', '这是通过终端命令使用的工具，具体命令和参数以项目说明为准。'),
    'app': ('应用或服务', '这是应用或服务项目，使用前需要核对安装方式、配置和运行条件。'),
    'desktop': ('桌面软件', '这是在电脑上使用的桌面软件，优先查看作者发布的安装包。'),
    'plugin': ('插件', '这是安装到其他软件中使用的扩展，需要先确认支持的软件和版本。'),
    'unknown': ('类型待确认', '目前还不能确认它的具体使用方式，可以先查看作者简介和项目目录。'),
}

# Each item is shown only when its topic is present in the material already read.
TOPICS = [
    (r'供应商切换|管理供应商|管理供应商与模型|统一管理供应商|\bprovider switching\b', '管理模型供应商', '集中配置并切换模型供应商，使用前需准备对应账号或密钥'),
    (r'协议转换|\bprotocol conversion\b', '转换接口协议', '在不同接口协议之间进行转换，支持范围以项目文档为准'),
    (r'会话管理|\bsession management\b', '管理会话', '集中整理和操作会话'),
    (r'界面增强|\b(?:ui enhancements?|interface enhancements?)\b', '调整使用界面', '通过界面增强选项调整阅读和操作体验'),
    (r'\b(?:coding assistant|code assistant|code completion|ai coding|code generation)\b|编程助手|代码补全|代码生成', '辅助编写代码', '参考代码生成、补全或编程协作能力，具体工作方式以项目说明为准'),
    (r'\b(?:tool[ _-]?(?:use|calling)|function[ _-]?calling)\b|工具调用', '调用外部工具', '让模型通过工具或函数与外部程序协作'),
    (r'\b(?:rag|retrieval[ -]augmented|semantic search)\b|检索增强|语义检索', '结合知识库回答问题', '检索已有资料，再结合资料生成回答'),
    (r'\b(?:vision|image understanding|image analysis|multimodal)\b|图像理解|多模态', '理解图片内容', '处理图像输入，提取或分析图片中的信息'),
    (r'\b(?:agents?|agentic)\b|智能体', '组织智能体任务', '参考智能体如何组合多个步骤完成任务'),
    (r'\b(?:pdf|document processing|document understanding)\b|文档处理', '处理文档', '读取或分析文档内容；支持的格式需要查看对应说明'),
    (r'\b(?:summari[sz](?:ation|e|ing)|summaries)\b|摘要|总结', '提炼内容摘要', '将较长内容整理成摘要或要点'),
    (r'\b(?:text classification|classify text|classification)\b|文本分类', '对内容进行分类', '按照给定类别组织或判断文本内容'),
    (r'\b(?:structured outputs?|json outputs?|data extraction)\b|结构化输出|信息抽取', '提取结构化信息', '把内容整理成字段、JSON 等便于程序处理的形式'),
    (r'\b(?:evaluations?|evals|test suites?)\b|评估|评测', '检查模型效果', '用评估流程比较输出质量或验证任务表现'),
    (r'\b(?:note[ -]?taking|knowledge base|backlinks)\b|笔记|知识库|双链', '整理笔记与知识', '记录和组织资料，具体关联方式以项目说明为准'),
    (r'\b(?:speech recognition|transcription|speech[ -]to[ -]text)\b|语音转写', '将语音转成文字', '从音频内容中识别文字'),
    (r'\b(?:ocr|optical character recognition)\b|文字识别', '识别图片中的文字', '从图片或扫描材料中提取文字'),
    (r'\b(?:web scraping|web scraper|web crawling)\b|网页抓取|网络爬虫', '采集网页信息', '获取并整理网页中的内容'),
    (r'\b(?:workflow automation|automate workflows)\b|工作流自动化', '连接自动化流程', '将多个处理步骤组合成工作流'),
]


def plain(text):
    text = re.sub(r'```[\s\S]*?```', '', str(text or ''))
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]*>', '', text)
    return re.sub(r'[*`#]', '', text).strip()


def relevant_readme(text):
    lines, skipped_level = [], 0
    for line in str(text or '').splitlines():
        heading = re.match(r'^\s*(#{1,6})\s+(.+)', line)
        if heading and skipped_level and len(heading[1]) <= skipped_level: skipped_level = 0
        if heading and re.search(r'sponsors?|advertis|contribut|acknowledg|donat|赞助|广告|致谢|交流与支持', heading[2], re.I): skipped_level = len(heading[1])
        if not skipped_level: lines.append(line)
    return '\n'.join(lines)


def project_guide(analysis):
    d = analysis or {}
    kind = d.get('kind', 'unknown')
    label, summary = KINDS.get(kind, KINDS['unknown'])
    source = 'README' if d.get('readme') and not d.get('degraded') else '作者简介'
    text = plain(relevant_readme(d.get('readme')) if source == 'README' else d.get('what') or d.get('description'))
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    capabilities = []
    for pattern, title, description in TOPICS:
        evidence = next((line for line in lines if re.search(pattern, line, re.I)
            and not re.search(r'\b(?:not supported|unsupported|does not support|without support)\b|不支持|尚未支持|未实现', line, re.I)), '')
        if evidence:
            detail = ('参考相关代码示例，' if kind == 'examples' else '') + description + '。'
            capabilities.append(dict(title=title, detail=detail, evidence=evidence[:240], source=source))
    capabilities = capabilities[:4]
    if capabilities:
        names = '、'.join(c['title'] for c in capabilities[:3])
        if kind == 'examples': summary = f'这是一套代码示例与教程，帮助你学习{names}，再把对应案例改进自己的项目。'
        elif kind in ('app', 'cli', 'library', 'plugin'):
            summary += f'已读取的资料提到了：{names}。'
    original = plain(d.get('what') or d.get('description') or '')
    if kind != 'api-service' and re.search(r'[\u4e00-\u9fff]{8,}', original): summary = original[:240]
    usage = {
        'api-service': '打开接入文档，申请服务方的 API Key，再在客户端设置 API 地址、Key 和模型。GitHub Token 用于读取仓库，不能作为这个 API 服务的 Key。',
        'examples': '先挑一个与你需求接近的案例，打开该目录或 Notebook，按它自己的依赖、密钥和运行说明操作。整个仓库通常没有统一启动按钮。',
        'awesome': '从目录中挑选条目，再进入对应项目查看使用说明。',
        'prompts': '选择合适的提示词，按你的任务修改，再粘贴到对应模型中。',
        'dataset': '先核对数据格式、许可证与处理脚本，再下载需要的部分。',
    }.get(kind, '先阅读项目的安装与使用章节；下方运行条件和命令仍需逐项核对。')
    return dict(kind_label=label, summary=summary, capabilities=capabilities, usage=usage,
        original=original, source=source,
        note='以下为已读取资料中的主题解读，具体支持范围请核对对应文档。' if capabilities else '暂未从已读取资料中提取到明确功能，请展开作者原文核对。')


