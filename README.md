# better-genshin-impact-log-nofi
better genshin impact log monitoring and process listening, keyword search and alert notification.
对BGI的日志内容进行关键字监控和进程监听，并进行通知

# 解决问题
BGI的0.64.0版本，不知道为什么，在执行连续配置组的时候，会在移动大地图的时候，移动错误，并退出自动化，然后还没有通知。
为了解决这个问题写了这个工具。
该工具也有利于其他情况下，BGI通知系统不通知以便通过读log来进行通知。
本来24小时的连续配置组，结果运行1小时就中断了，剩余23小时都在浪费电，真遭不住。

# 功能
1.对指定进程是否存在进行监听->修改config.ini中的[exe]下的键。e1键名不能改，其他随便改。主要是对原神和BGI进程进行监听。
2.对日志文件指定内容进行监控，关键字修改config.ini中的[keyword]下的键。同样k1的键名不能改。
3.搜索到指定关键字或进程不存在后，会发送一个通知到企业微信。目前仅支持企业微信，有其他需要告诉我，改起来也快。

# 操作手册。
1.下载exe，顺便下一个config.ini。或者下载zip并运行main.py，当然记得安装库
2.修改config.ini文件，必须在文件同文件夹内。
3.修改[wechat]企业微信的key值。
4.修改[folder]file值，指向的是BGI的log目录，如D:\genshin\BGI-sync\log  log文件夹内应该有better-genshin-impact20260903.log 这样的文件
5.修改你要监听的关键字[keyword]
示例：
# 仅监听日志内容，message
k1 = message:任务中断:"取消自动任务"
# 需要同时符合level等级为[INF]且module为BetterGenshinImpact.GameTask.TaskRunner 且内容message:→ "任务结束"
k2 = level:INF;module:BetterGenshinImpact.GameTask.TaskRunner;message:→ "任务结束"
# 仅监听是否存在level等级为[ERR]的日志
;k3 = level:ERR
# 子进程监听，我觉得没啥用
;k4 = session:ChildSession:S4
6.[loop-time] 下time。指的是重复检测的循环时间间隔。秒。建议600以上，否则你的手机要💥
7.[exe]指的是你要监听的进程名，可以有多个，要带.exe

# 注意：
[log_offset]下级指的是对指定log文件检测到的关键字最后时间戳+001，以便排除log中已经通知过的日志内容。解决在桌面分身下面，BGI没法关闭，log锁定没法修改的问题。
config.ini会在每次循环前自动重新读取，你可以在桌面分身里面暂停配置组然后修改config.ini，然后把程序运行在主系统里，不影响远程不能关BGI和log操作的问题。
支持多天，自动读新日志。
支持同时单日的多个日志。（多开造成的）

应该把想到的都改了。
也可以跟BGI通知一样，加个截图，但是我感觉没必要，毕竟通知你的时候你就知道已经停了。
