"""
    1.每次循环前，重新拉取config.ini，以便修改后立即生效，解决桌面分身问题，进程可以执行在主系统而不需要停止分身
    2.每个日志文件独立维护读取偏移时间，保存在[log_offset]，key=日志文件名
    3.日期更新后，自动删除ini [log_offset]中非今日日志的key
    4.当日所有待扫描日志文件，即使没有命中关键词，也写入ini初始偏移00:00:00.000，避免每轮从头扫描
"""

import configparser
import os
from datetime import datetime, timedelta
import time
import psutil
import sys
import re
from typing import Iterator, Optional, List, Dict, Tuple
import nofi
import logRead

# pyinstaller -F --name "BGI日志和进程监控" -i favicon.ico main.py

def send_text(cfg, hand, text):
    """企业微信markdown通知"""
    webhook_key = cfg.get("wechat", "key")
    print("-----------------执行信息发送-----------------")
    qy_msg = nofi.QyWechatWebhook(webhook_key)
    now_time = datetime.now().strftime("%Y‑%m‑%d %H:%M:%S")
    markdown_text = f"""### BGI日志监测工具
> <font color="info">状态：</font><font color="warning">{hand}</font>
- <font color="info">信息：</font>{text}
- <font color="info">触发时间：</font>{now_time}
"""
    res3 = qy_msg.send_markdown(markdown_text)
    print("---信息发送回折：", res3)


def load_config(ini_path="config.ini") -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not os.path.exists(ini_path):
        raise FileNotFoundError(f"配置文件 {ini_path} 不存在")
    cfg.read(ini_path, encoding="utf-8")
    return cfg


def save_log_offset_only(ini_path: str, log_offset_data: Dict[str, str]):
    """只更新 [log_offset] 区块，保留ini所有#注释，其他section完全不动"""
    if not os.path.exists(ini_path):
        return
    with open(ini_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    new_block_lines = ["[log_offset]"]
    for fname, timestr in log_offset_data.items():
        new_block_lines.append(f"{fname} = {timestr}")
    new_block = "\n".join(new_block_lines)

    pattern = re.compile(
        r"\[log_offset\].*?(?=\n\[|\Z)",
        re.DOTALL
    )
    if pattern.search(raw_text):
        new_text = pattern.sub(new_block, raw_text)
    else:
        new_text = raw_text.rstrip("\n") + "\n\n" + new_block

    with open(ini_path, "w", encoding="utf‑8") as f:
        f.write(new_text)


def parse_keyword_rule(raw_value: str) -> Dict[str, Optional[str]]:
    """
    支持字段：level, session, module, message
    格式示例：session:ChildSession:S4 ; level:ERR
    """
    rule: Dict[str, Optional[str]] = {
        "level": None,
        "session": None,
        "module": None,
        "message": None
    }
    raw = raw_value.strip().strip('"')
    if ";" not in raw and ":" not in raw:
        rule["message"] = raw
        return rule

    parts = raw.split(";")
    for p in parts:
        p = p.strip()
        if ":" not in p:
            continue
        k, _, v = p.partition(":")
        k = k.strip()
        v = v.strip()
        if k in rule:
            rule[k] = v
    return rule


def read_keyword_rules(cfg) -> List[Tuple[str, Dict[str, Optional[str]], str]]:
    raw_dict = dict(cfg["keyword"])
    rule_list = []
    for rule_key, raw_val in raw_dict.items():
        r = parse_keyword_rule(raw_val)
        rule_list.append((rule_key, r, raw_val))
    return rule_list


def is_log_match_rule(log_dict: Dict, rule: Dict[str, Optional[str]]) -> bool:
    if rule["level"] is not None:
        if log_dict.get("level") != rule["level"]:
            return False
    if rule["session"] is not None:
        s = log_dict.get("session", "") or ""
        if rule["session"] not in s:
            return False
    if rule["module"] is not None:
        m = log_dict.get("module", "") or ""
        if rule["module"] not in m:
            return False
    if rule["message"] is not None:
        msg = log_dict.get("message", "") or ""
        if rule["message"] not in msg:
            return False
    return True


def get_log_file_name(cfg) -> list:
    log_folder = cfg["folder"]["file"]
    today_str = datetime.now().strftime("%Y%m%d")
    print(f"今日日期标记: {today_str}")
    target_log_files = []
    if not os.path.isdir(log_folder):
        print(f"日志目录不存在 {log_folder}")
        return target_log_files
    for filename in os.listdir(log_folder):
        full_path = os.path.join(log_folder, filename)
        if os.path.isfile(full_path):
            if filename.lower().endswith(".log"):
                if today_str in filename:
                    target_log_files.append(full_path)
    print("\n符合条件文件名列表(今日日志):")
    for i in target_log_files:
        print(i)
    #print(target_log_files)
    return target_log_files


def ms_to_time_str(total_ms: int) -> str:
    h = total_ms // (3600 * 1000)
    rem = total_ms % (3600 * 1000)
    m = rem // (60 * 1000)
    rem = rem % (60 * 1000)
    s = rem // 1000
    ms = rem % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def clean_log_offset(cfg, today_str: str, ini_path: str):
    log_offset_data = dict(cfg["log_offset"]) if "log_offset" in cfg.sections() else {}
    remove_keys = []
    for log_filename in log_offset_data.keys():
        if today_str not in log_filename:
            remove_keys.append(log_filename)
    if remove_keys:
        print(f"\n>>>清理log_offset，删除非今日日志记录：{remove_keys}")
        for k in remove_keys:
            del log_offset_data[k]
        save_log_offset_only(ini_path, log_offset_data)
        if "log_offset" in cfg.sections():
            for rk in remove_keys:
                if rk in cfg["log_offset"]:
                    del cfg["log_offset"][rk]


def read_log_file(cfg, ini_path: str) -> Tuple[List[Dict], Dict[str, Dict[str, Dict]]]:
    """
    返回 (all_hit_result, file_stat)
    file_stat: {日志文件名: {rule_key: {"count":int, "last_hit": Optional[dict]}}}
    """
    today_str = datetime.now().strftime("%Y%m%d")
    clean_log_offset(cfg, today_str, ini_path)

    logfilename_list = get_log_file_name(cfg)
    all_hit_result = []
    file_stat: Dict[str, Dict[str, Dict]] = {}

    rule_list = read_keyword_rules(cfg)
    if not rule_list:
        print("[keyword] 没有配置任何筛选规则，直接返回空")
        return [], file_stat

    log_offset_data: Dict[str, str] = {}
    if "log_offset" in cfg.sections():
        log_offset_data = dict(cfg["log_offset"])

    for log_path in logfilename_list:
        filepath = os.path.basename(log_path)
        # 初始化该文件的规则统计
        per_file_rule_stat = {}
        for rk, _, _ in rule_list:
            per_file_rule_stat[rk] = {"count": 0, "last_hit": None}
        file_stat[filepath] = per_file_rule_stat

        if filepath not in log_offset_data:
            start_time_str = "00:00:00.000"
            log_offset_data[filepath] = start_time_str
            save_log_offset_only(ini_path, log_offset_data)
            if "log_offset" not in cfg.sections():
                cfg["log_offset"] = {}
            cfg["log_offset"][filepath] = start_time_str
            print(f"检测到新日志文件[{filepath}]，写入ini初始读取起点 {start_time_str}")
        else:
            start_time_str = log_offset_data[filepath]

        print(f"\n>>>处理日志文件：{filepath}，读取起点：{start_time_str}")
        file_max_hit_ms = 0

        for log_dict in logRead.filter_log_after_time(log_path, start_time_str):
            hit_matches = []
            for rule_key, rule_dict, rule_raw in rule_list:
                if is_log_match_rule(log_dict, rule_dict):
                    hit_matches.append({
                        "rule_key": rule_key,
                        "rule_raw": rule_raw
                    })
                    # 当前文件下该规则计数更新
                    fs = file_stat[filepath][rule_key]
                    fs["count"] += 1
                    fs["last_hit"] = log_dict

            if hit_matches:
                hit_item = {
                    "log_file": filepath,
                    "time_str": log_dict["time_str"],
                    "time_ms": log_dict["time_ms"],
                    "level": log_dict["level"],
                    "session": log_dict["session"],
                    "module": log_dict["module"],
                    "message": log_dict["message"],
                    "hit_matches": hit_matches
                }
                all_hit_result.append(hit_item)
                if log_dict["time_ms"] > file_max_hit_ms:
                    file_max_hit_ms = log_dict["time_ms"]

        if file_max_hit_ms > 0:
            next_start_ms = file_max_hit_ms + 1
            new_start_str = ms_to_time_str(next_start_ms)
            log_offset_data[filepath] = new_start_str
            save_log_offset_only(ini_path, log_offset_data)
            cfg["log_offset"][filepath] = new_start_str
            print(f">>>更新[{filepath}]读取偏移 → {new_start_str} (+1ms，防止重复告警)")
        else:
            print(f">>>[{filepath}]本次扫描没有命中关键词，保留ini已存在的偏移记录，不修改")

    return all_hit_result, file_stat


def read_exe_key(cfg) -> dict:
    exe_dict = dict(cfg["exe"])
    print("进程字典", exe_dict)
    return exe_dict


def get_not_running_process(cfg) -> list:
    proc_dict = read_exe_key(cfg)
    running_names = set()
    for proc in psutil.process_iter(["name"]):
        try:
            running_names.add(proc.info["name"].lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    not_run = []
    for _, exe_name in proc_dict.items():
        if exe_name.lower() not in running_names:
            not_run.append(exe_name)
    print("未执行的进程名", not_run)
    return not_run


def main_loop(ini_path):
    while True:
        try:
            print("\n========重新加载配置========")
            cfg = load_config(ini_path)
            loop_time = int(cfg.get("loop-time", "time"))
            print("循环时间(秒)：", loop_time)

            print("\n----------------开始进程检查----------------")
            exe_run_list = get_not_running_process(cfg)
            if exe_run_list:
                send_text(cfg, "未发现进程", str(exe_run_list))

            print("\n----------------开始执行日志检查----------------")
            hit_list, file_stat = read_log_file(cfg, ini_path)

            # ==========按每个日志文件分别汇总打印 ==========
            print("\n" + "="*90)
            print("【本轮扫描，按日志文件独立命中统计汇总】")
            wechat_notify_parts = []
            for fname, rule_dict in file_stat.items():
                # 判断该文件有没有任意一条命中
                has_any_hit = any(s["count"] > 0 for s in rule_dict.values())
                if not has_any_hit:
                    line = f"{fname}： 未命中"
                    print(line)
                    wechat_notify_parts.append(line)
                else:
                    print(f"{fname}：")
                    wechat_notify_parts.append(f"{fname}：")
                    for rk, stat in rule_dict.items():
                        cnt = stat["count"]
                        last_hit = stat["last_hit"]
                        if last_hit:
                            out_line = f"  规则 {rk:4s} | 总命中:{cnt:4d} | 最后命中时间:{last_hit['time_str']} | message:{last_hit['message']}"
                        else:
                            out_line = f"  规则 {rk:4s} | 总命中:{cnt:4d} | 本轮无命中"
                        print(out_line)
                        wechat_notify_parts.append(out_line)
            print("="*90 + "\n")

            # 企业微信推送
            if hit_list:
                notify_text = "\n".join(wechat_notify_parts)
                send_text(cfg, "日志匹配命中", notify_text)
            else:
                print("本次无关键词命中，跳过发送")

        except Exception as e:
            print(f"本轮执行发生异常：{e}")
            try:
                send_text(cfg, "软件错误", f"监控工具异常：{str(e)}")
            except Exception:
                pass

        next_run_time = datetime.now() + timedelta(seconds=loop_time)
        print(f"\n等待 {loop_time} 秒({loop_time/60:.1f}分钟)，下次检查执行时间：{next_run_time.strftime('%Y‑%m‑%d %H:%M:%S')}")
        print("========================================================")
        print("========================================================")
        print("========================================================\n")
        time.sleep(loop_time)


def get_app_path():
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return base_path


def check_config(ini_path: str):
    required_sections = {
        "wechat": ["key"],
        "folder": ["file"],
        "keyword": ["k1"],
        "loop-time": ["time"],
        "exe": ["e1"],
        "log_offset": []
    }
    if not os.path.exists(ini_path):
        return False, f"错误：配置文件 {ini_path} 不存在"
    cfg = configparser.ConfigParser()
    try:
        cfg.read(ini_path, encoding="utf‑8")
    except Exception as e:
        return False, f"错误：配置文件解析失败 {e}"

    for sec_name, key_list in required_sections.items():
        if sec_name not in cfg.sections():
            if sec_name == "log_offset":
                continue
            return False, f"错误：ini缺少节点 [{sec_name}]"
        for k in key_list:
            if k not in cfg[sec_name]:
                return False, f"错误：节点 [{sec_name}] 缺少键 {k}"
            val = cfg[sec_name][k].strip()
            if len(val) == 0:
                return False, f"错误：[{sec_name}] 下键 {k} 值为空"
    return True, "配置校验通过"


if __name__ == "__main__":
    app_base = get_app_path()
    config_file = os.path.join(app_base, "config.ini")
    ok, msg = check_config(config_file)
    print(msg)
    if not ok:
        input("\n配置异常，按回车键退出程序...")
        sys.exit(1)

    print("开始执行主程序...")
    main_loop(config_file)
