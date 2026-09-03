import re
import json
from dataclasses import dataclass
from typing import Iterator, Optional, List, Dict

TIME_PATTERN = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\]")
HEAD_PATTERN = re.compile(r"^\s*\[(.*?)\]\s*\[(.*?)\]\s*(.*)$")


@dataclass
class BgiLogEntry:
    """BetterGenshinImpact 单条日志数据模型"""
    time_ms: int
    time_str: str
    level: Optional[str]
    session: Optional[str]
    module: Optional[str]
    message: str

    def to_dict(self) -> Dict:
        return {
            "time_ms": self.time_ms,
            "time_str": self.time_str,
            "level": self.level,
            "session": self.session,
            "module": self.module,
            "message": self.message
        }


def parse_time_str_to_ms(time_str: str) -> int:
    hh_str, mm_str, sec_ms_str = time_str.split(":")
    ss_str, ms_str = sec_ms_str.split(".")
    total = int(hh_str) * 3600 * 1000 + int(mm_str) * 60 * 1000 + int(ss_str) * 1000 + int(ms_str)
    return total


def parse_bgi_log_file(file_path: str) -> Iterator[BgiLogEntry]:
    last_time_ms: Optional[int] = None
    last_time_str: Optional[str] = None
    last_level: Optional[str] = None
    last_session: Optional[str] = None
    last_module: Optional[str] = None

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            raw_line = line.rstrip("\n\r")
            if not raw_line.strip():
                continue

            match_time = TIME_PATTERN.match(raw_line)
            if match_time:
                hh, mm, ss, fff = match_time.groups()
                time_str = f"{hh}:{mm}:{ss}.{fff}"
                time_ms = parse_time_str_to_ms(time_str)
                remain = raw_line[match_time.end():].strip()

                head_match = HEAD_PATTERN.match(remain)
                level: Optional[str] = None
                session: Optional[str] = None
                module: Optional[str] = None
                msg_body = ""

                if head_match:
                    level = head_match.group(1)
                    session = head_match.group(2)
                    after_head = head_match.group(3).strip()
                    sp = after_head.split(" ", maxsplit=1)
                    if len(sp) >= 2:
                        module = sp[0]
                        msg_body = sp[1]
                    elif len(sp) == 1:
                        module = sp[0]
                        msg_body = ""
                    else:
                        module = None
                        msg_body = after_head

                # ========= 【修复】清理竖线 | 前缀，去除噪音 =========
                # 去掉开头 | 符号以及空白
                msg_body = re.sub(r"^\s*\|\s*", "", msg_body).strip()

                # 过滤：消息为空，直接跳过本条日志，不产出对象（消除重复空行噪音）
                if not msg_body:
                    # 更新上下文，但不yield，跳过这条噪音行
                    last_time_ms = time_ms
                    last_time_str = time_str
                    last_level = level
                    last_session = session
                    last_module = module
                    continue

                last_time_ms = time_ms
                last_time_str = time_str
                last_level = level
                last_session = session
                last_module = module

                yield BgiLogEntry(
                    time_ms=time_ms,
                    time_str=time_str,
                    level=level,
                    session=session,
                    module=module,
                    message=msg_body
                )
            else:
                # 无时间头，多行继承
                if last_time_ms is not None:
                    msg_body = raw_line.strip()
                    msg_body = re.sub(r"^\s*\|\s*", "", msg_body).strip()
                    if msg_body:
                        yield BgiLogEntry(
                            time_ms=last_time_ms,
                            time_str=last_time_str,
                            level=last_level,
                            session=last_session,
                            module=last_module,
                            message=msg_body
                        )


def filter_log_after_time(file_path: str, filter_after_time_str: str) -> Iterator[Dict]:
    filter_ms = parse_time_str_to_ms(filter_after_time_str)
    for entry in parse_bgi_log_file(file_path):
        if entry.time_ms >= filter_ms:
            yield entry.to_dict()


def filter_cancel_task(file_path: str) -> Iterator[Dict]:
    for entry in parse_bgi_log_file(file_path):
        if '任务中断:"取消自动任务"' in entry.message:
            yield entry.to_dict()


def filter_log_level(file_path: str, level="ERR") -> Iterator[Dict]:
    for entry in parse_bgi_log_file(file_path):
        if entry.level == level:
            yield entry.to_dict()


def filter_task_runner_module(file_path: str, module="BetterGenshinImpact.GameTask.TaskRunner") -> Iterator[Dict]:
    target_mod = module
    for entry in parse_bgi_log_file(file_path):
        if entry.module == target_mod:
            yield entry.to_dict()


def filter_two_consecutive_logs(file_path: str, log1='任务中断:"取消自动任务"', log2='→ "任务结束"') -> Iterator[Dict]:
    prev_entry: Optional[BgiLogEntry] = None
    for curr_entry in parse_bgi_log_file(file_path):
        if prev_entry is not None:
            cond1 = log1 in prev_entry.message
            cond2 = log2 in curr_entry.message
            if cond1 and cond2:
                yield curr_entry.to_dict()
        prev_entry = curr_entry


def print_log_dict(d: Dict, prev_d: Optional[Dict] = None):
    if prev_d and d['time_str'] == prev_d['time_str'] and d['level'] == prev_d['level'] and d['session'] == prev_d['session'] and d['module'] == prev_d['module']:
        print(f"    {d['message']}")
    else:
        print(f"[{d['time_str']}] [{d['level']}] [{d['session']}] {d['module']} | {d['message']}")

def get_all_log_levels(file_path: str) -> Dict[str, int]:
    """获取日志中全部日志等级，返回 {等级:计数}"""
    level_counter: Dict[str, int] = {}
    for entry in parse_bgi_log_file(file_path):
        lv = entry.level
        if lv is not None:
            if lv in level_counter:
                level_counter[lv] += 1
            else:
                level_counter[lv] = 1
    return level_counter

def get_all_log_as_dict_list(file_path: str) -> List[Dict]:
    """无任何筛选，读取全部日志，返回list，每条日志是字典"""
    result = []
    for entry in parse_bgi_log_file(file_path):
        result.append(entry.to_dict())
    return result


if __name__ == "__main__":
    LOG_FILE = r"better-genshin-impact202609021.txt"

    # time_str 时间戳：[18:30:35.247]
    # level ：等级 [INF]  INF  ERR DBG  WRN
    # session ：子进程[ChildSession:S4:P1256:T1788265629219]
    # module ：模块 BetterGenshinImpact.GameTask.TaskRunner
    # message： 内容：任务中断:"取消自动任务"

    # ========== 无筛选，全部日志读入list[dict] ==========
    all_log_list: List[Dict] = get_all_log_as_dict_list(LOG_FILE)
    print(f"全部日志总条数：{len(all_log_list)}")
    '''
    # 取第0条（第一条）日志字典
    if all_log_list:
        first = all_log_list[0]
        print("\n第一条日志字典：")
        print(first)
        print(f"时间：{first['time_str']}")
        print(f"等级：{first['level']}")
    '''
    # 循环遍历全部日志
    for log_dict in all_log_list:
        print_log_dict(log_dict)


    ###################### 根据level等级筛选
    '''
    # 找到并输出指定等级的日志 INF  ERR DBG  WRN
    print("\n======== 2.ERR错误日志 list[dict] ========")
    err_log_list: List[Dict] = list(filter_log_level(LOG_FILE, "ERR"))
    print(f"ERR日志命中条数：{len(err_log_list)}")
    for d in err_log_list:
        print_log_dict(d)
    '''
    '''
    # ========== 新增：输出日志全部等级类型以及计数 ==========
    print("======== 日志中所有等级类型统计 ========")
    level_stats = get_all_log_levels(LOG_FILE)
    for level_name, count in sorted(level_stats.items()):
        print(f"等级：{level_name}，出现次数：{count}")
    print(f"一共识别到 {len(level_stats)} 种日志等级\n")
    '''
    
    ###################### 根据模块筛选
    # module ：模块 BetterGenshinImpact.GameTask.TaskRunner
    # BetterGenshinImpact.App
    # BetterGenshinImpact.Core.Script.Dependence.Log
    # BetterGenshinImpact.GameTask.AutoFight.Script.ConditionEvaluator
    # BetterGenshinImpact.GameTask.AutoPick.AutoPickTrigger
    # BetterGenshinImpact.GameTask.AutoSkip.AutoSkipTrigger
    # BetterGenshinImpact.GameTask.Common.TaskControl
    # BetterGenshinImpact.GameTask.TaskRunner
    # BetterGenshinImpact.GameTask.TaskTriggerDispatcher
    # BetterGenshinImpact.Service.Instance.InstanceService
    # BetterGenshinImpact.Service.ScriptService
    # BetterGenshinImpact.View.MainWindow
    # BetterGenshinImpact.ViewModel.Pages.HotKeyPageViewModel
    # BetterGenshinImpact.ViewModel.Pages.ScriptControlViewModel
    '''
    # ========== 1：扫描全部日志，收集所有不为None的module类型集合 ==========
    print("==== 扫描日志，所有不为None的module ====")
    module_set = set()
    for entry in parse_bgi_log_file(LOG_FILE):
        if entry.module is not None and entry.module.strip() != "":
            module_set.add(entry.module)
    for m in sorted(module_set):
        print(f" - {m}")
    print(f"\n一共识别到 {len(module_set)} 个非空模块\n")
    '''
    '''
    # 找到并输出指定模块的日志
    print("\n========3.TaskRunner模块日志 list[dict] ========")
    runner_log_list: List[Dict] = list(filter_task_runner_module(LOG_FILE, "BetterGenshinImpact.GameTask.TaskRunner") )
    print(f"TaskRunner日志命中条数：{len(runner_log_list)}")
    for d in runner_log_list:
        print_log_dict(d)
    '''
    ###################### 根据内容筛选
    '''
    print("======== 1.任务中断:\"取消自动任务\" 保存为字典列表list[dict] ========")
    cancel_log_list: List[Dict] = list(filter_cancel_task(LOG_FILE))
    print(f"命中条数：{len(cancel_log_list)}")

    # 分别输出符合指定内容的日志
    for idx, log_dict in enumerate(cancel_log_list):
        print(f"\n-----第 {idx+1} 条日志 -----")
        log_time = log_dict["time_str"]
        log_level = log_dict["level"]
        log_session = log_dict["session"]
        log_module = log_dict["module"]
        log_msg = log_dict["message"]
        print(f"time_str: {log_time}")
        print(f"level: {log_level}")
        print(f"session: {log_session}")
        print(f"module: {log_module}")
        print(f"message: {log_msg}")

    # 获取时间最晚日志
    if cancel_log_list:
        latest_log_dict = max(cancel_log_list, key=lambda x: x["time_ms"])
        print("\n===== 符合条件，时间最晚的日志字典 =====")
        print(latest_log_dict)
        latest_t = latest_log_dict["time_str"]
        print("最晚一条日志时间：", latest_t)
        print_log_dict(latest_log_dict)
    else:
        print("\n===== 没有找到任务中断:\"取消自动任务\"日志 =====")
    '''
    '''
    print("\n========4.取消任务紧接着任务结束，取后一条日志字典列表 ========")
    cancel_end_list: List[Dict] = list(filter_two_consecutive_logs(LOG_FILE,log1 = '任务中断:"取消自动任务"' ,log2 = '→ "任务结束"'))
    print(f"命中条数：{len(cancel_end_list)}")
    for d in cancel_end_list:
        print_log_dict(d)
    '''
    
    ###################### 根据时间戳筛选
    '''
    # ======================================================
    # 组合示例：只看00:04:00之后的ERR日志（时间过滤 + 条件过滤）
    # ======================================================
    print("\n======== 组合示例：只看00:04:00之后的ERR日志 ========")
    for d in filter_log_after_time(LOG_FILE, "00:57:00.000"):
        if d["level"] == "ERR":
            print_log_dict(d)
    '''

    # ======================================================
    # 只看 00:04:00 之后，同时满足任务中断:"取消自动任务"
    # ======================================================
    '''
    print("\n只看 00:04:00 之后，同时满足任务中断:\"取消自动任务\"")
    for d in filter_log_after_time(LOG_FILE, "00:04:00.000"):
        if '任务中断:"取消自动任务"' in d["message"]:
            print_log_dict(d)
    '''
    '''
    # ======================================================
    # 将筛选结果写入文件示例（filter_cancel_task输出dict）
    # ======================================================
    print("\n==== 将筛选结果写入result.txt示例 ====")
    with open("result.txt", "w", encoding="utf-8") as f:
        for item_dict in filter_cancel_task(LOG_FILE):
            line = f"[{item_dict['time_str']}] [{item_dict['level']}] [{item_dict['session']}] {item_dict['module']} | {item_dict['message']}\n"
            f.write(line)

    # 导出json示例
    # with open("cancel_logs.json","w",encoding="utf-8") as f:
    #     json.dump(cancel_log_list, f, ensure_ascii=False, indent=2)

'''