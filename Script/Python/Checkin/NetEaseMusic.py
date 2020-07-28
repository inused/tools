#-*- encoding:utf-8 -*-
import os
import pytz
import time
import json
import js2py
import pickle
import codecs
import string
import random
import base64
import hashlib
import requests
from datetime import datetime
from Crypto.Cipher import AES
from urllib.parse import quote
from bs4 import BeautifulSoup


###############################################
# 注意点在 class NetEaseMusic 的注释中写的很详细 #
###############################################


######################################### 需修改部分 start #########################################
# 手机号 必填
phone = ""
# 密码 必填
password = ""
# 手机国别区号 中国:86; 美国:1; 默认86,根据实际情况填写
countryCode = "86"
# 刷歌时少量多次提交,该参数为每次提交歌曲数量,默认50 与参数 cyclesNumMax 配合,两者相乘为刷歌数量
# 网易云限制每天上限总共为300首 两者相乘数量越多越有可能一次刷完300首,但刷歌过多后续有可能会出现大量重复歌曲导致无法刷到上限
songNum = 50
# 刷歌时若迟迟刷不到300首歌,最大循环次数,刷歌提交数据循环次数,与参数 songNum 相配合,两者相乘为刷歌数量
cyclesNumMax = 8
# 是否从热门推荐中刷歌,默认False否,不开启的话只从每日个性化推荐中提取歌曲,开启后添加从移动端首页获取热门推荐歌单
isGetPopular = False
# server酱 密钥,不填写的话程序异常时不会通过server酱推送消息
serverChainKey = ""
######################################### 需修改部分 end #########################################


def main():
    # 实例化
    # 使用的参数: 用户名、密码、区号、每次回传歌曲数量、回传歌曲次数、server酱密钥、是否获取热门推荐歌曲
    # 有需要自行修改实例化时所需的参数 (用户名/密码)必填,其他都有默认值,可看注释
    music = NetEaseMusic(phone, password, countryCode=countryCode, songNum=songNum,
                    cyclesNumMax=cyclesNumMax, serverChainKey=serverChainKey, isGetPopular=isGetPopular)
    # 执行主函数
    music.main()

class NetEaseMusic():
    """网易云音乐签到、刷歌工具 支持手机号密码登录,支持cookies登录
        1.cookies本地保存文件有两个 保存在当前脚本所在文件夹,均可自动修改
            文件名格式: 当前脚本文件名.cookieStr 和 当前脚本文件名.cookieJar
            比如 当前脚本文件名 NetEaseMusic.py 则两个cookies文件名分别为
                NetEaseMusic.py.cookieStr 可手动修改,可从浏览器提取cookie字符串 https://jingyan.baidu.com/article/5d368d1ea6c6e33f60c057ef.html
                NetEaseMusic.py.cookieJar 不可手动修改,requests.session().cookies 持久化文件
        2.刷歌时从每日个性化推荐中获取歌曲, 可通过 isGetPopular 参数设置是否获取热门推荐(从移动端页面获取)
            因为是从日推(可以加上热门推荐)中获取歌曲,所以有可能出现数量不足300或者重复导致的刷歌数量达不到每日上限
            可以根据 playListInMobile 函数的实现方式自行添加其他获取歌曲的渠道
        3.只使用脚本时登录天数可能会出现长时间不增长的情况,每天真实听歌可以缓解
        4.加密算法参考 https://github.com/darknessomi/musicbox 配合抓包PC端网页分析获得
    ----------------------------
        username: 用户名(仅支持手机号) 
        password: 密码
        countryCode: 手机号区号,默认86(中国),1=美国/加拿大
        loginType: 登录方式 phone=手机号(仅支持手机号)
        songNum: 刷歌时少量多次提交,该参数为每次提交歌曲数量,默认50
                每天上限为300,数量越多越有可能一次刷完,但后续有可能会出现一天没法刷到上限的问题
        cyclesNumMax: 刷歌提交数据循环次数,与参数 songNum 相配合,两者相乘为刷歌数量
        isGetPopular: 是否获取热门推荐歌单,默认False不获取
        proxy:代理 默认不使用, 格式 http://127.0.0.1:10086
        verifySSL: 是否验证ssl证书,默认不验证 """
    # 当前脚本真实路径
    curPath = os.path.realpath(__file__)
    # 当前脚本所在文件夹
    curDir = os.path.dirname(curPath)
    # 当前脚本文件名
    curName = os.path.basename(curPath)
    # cookie文件路径 当前文件夹下
    cookieStrPath = '%s.cookieStr'%(curPath)
    # cookieJar持久化文件路径 当前文件夹下
    cookieJarPath = '%s.cookieJar'%(curPath)
    # 时区 东八区
    timezone = pytz.timezone('Asia/Shanghai')
    # 网易云音乐域名
    domain = 'https://music.163.com'
    # 移动端首页
    mobileIndex = 'https://y.music.163.com/m'
    # 可以获取数据的首页
    dataIndex = '%s/discover'%(domain)
    # 手机登录Weapi
    loginPhoneWeapi = '%s/weapi/login/cellphone'%domain
    # 账户信息获取api,不需要提交加密表单
    accountApi = '%s/api/nuser/account/get'%domain
    # 获取账号等级信息api 不需要提交加密表单,直接get方法获取
    levelApi = '%s/api/user/level'%domain
    # 获取账号等级信息Weapi 需要提交加密表单
    levelWeapi = '%s/weapi/user/level'%domain
    # 签到Weapi
    checkinWeapi = '%s/weapi/point/dailyTask'%domain
    # 听歌记录Weapi
    songRecordWeapi = '%s/weapi/v1/play/record?csrf_token='%domain
    # 每日个性推荐歌单Weapi
    playListWeapi = '%s/weapi/v1/discovery/recommend/resource'%domain
    # 每日个性推荐歌曲api
    dailySongApi = '%s/api/v2/discovery/recommend/songs'%domain
    # 获取歌单具体信息api 用来获取歌单中歌曲的ID
    playlistInfoWeapi = '%s/weapi/v3/playlist/detail?csrf_token='%domain
    # 听歌信息回传URL
    feedbackWeapi = '%s/weapi/feedback/weblog?csrf_token='%domain
    # 登录的账号信息
    accountProfile = {}
    accountAccount = {}
    # 播放列表id
    playlistIds = []
    # 个性推荐歌单与个性推荐歌曲中所有歌曲ID
    songIds = []
    # 已经刷过的歌曲ID
    songRecords = []
    # csrf token
    csrf = None
    # 对表单进行AES加密的初始化向量 固定值
    aesIV = '0102030405060708'
    # 表单一次AES加密密钥 固定值; 此外还有二次加密密钥,为随机16位字符串
    # 对 ["爱心", "女孩", "惊恐", "大笑"] 列表进行加密运算获得 https://s3.music.126.net/web/s/core_xxx.js
    aesNonce = '0CoJUm6Qyw8W8jud'
    # RSA加密密钥,用来加密表单二次AES加密的密钥,固定值
    # 对 ["流泪", "强"] 列表进行加密运算获得  https://s3.music.126.net/web/s/core_xxx.js
    rsaPubkey = '010001'
    # 对表单二次AES加密密钥进行RSA加密时对原始数据取模运算时的模数 固定值
    # 对一个包含52个表情的列表进行加密运算获得 https://s3.music.126.net/web/s/core_xxx.js
    modulus = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
    # 请求头
    userAgent = 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.1916.157 Safari/537.36'
    # 移动端请求头
    userAgentMobile = "Mozilla/5.0 (Linux; Android 8.0.0; Pixel 2 XL Build/OPD1.170816.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Mobile Safari/537.36"
    # 会话
    httpSession = requests.session()
    # 请求头
    httpSession.headers.update({'User-Agent': userAgent, 'Referer': domain})
    # 默认区号
    countryCodeDefault = '86'

    def __init__(self, username, password, countryCode='86', loginType='phone',
                songNum=50, cyclesNumMax=8, isGetPopular=False, proxy=None,
                verifySSL=False, serverChainKey=None):
        """网易云音乐签到、刷歌工具，刷歌时从每日个性化推荐中获取歌曲 支持手机号密码登录,支持cookies登录
            可通过 isGetPopular 参数设置是否获取热门推荐(从移动端页面获取)
            因为是从日推(可以加上热门推荐)中获取歌曲,所以有可能出现数量不足300或者重复导致的刷歌数量达不到每日上限
        ----------------------------
            username: 用户名(仅支持手机) 
            password: 密码
            countryCode: 手机号区号,默认86(中国),1=美国/加拿大
            loginType: 登录方式 phone=手机号(仅支持手机号)
            songNum: 刷歌时少量多次提交,该参数为每次提交歌曲数量,默认50
                    每天上限为300,数量越多越有可能一次刷完,但后续有可能会出现一天没法刷到上限的问题
            cyclesNumMax: 刷歌提交数据循环次数,与参数 songNum 相配合,两者相乘为一次刷歌次数
            isGetPopular: 是否获取热门推荐歌单,默认False不获取
            proxy:代理 默认不使用, 格式 http://127.0.0.1:10086
            verifySSL: 是否验证ssl证书,默认不验证
            serverChainKey: server酱密钥,未设置则不推送消息 """
        # 用户名
        self.username = username
        # 密码
        self.password = password
        # 电话区号
        self.countryCode = countryCode if countryCode else countryCodeDefault
        # 单次提交歌曲数量 默认50
        self.songNum = songNum if (songNum>0) else 50
        # 提交操作循环次数
        self.cyclesNumMax = cyclesNumMax
        # 代理
        if proxy:
            self.proxy = {'http': proxy, 'https': proxy}
            self.httpSession.proxies = self.proxy
        # 是否获取热门推荐歌曲
        self.isGetPopular = isGetPopular
        # 是否验证SSL整数
        self.verifySSL = verifySSL
        if not verifySSL:
            # 不验证ssl证书时会弹出警告信息,取消警告信息
            requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        # server酱密钥
        self.serverChainKey = serverChainKey

    def main(self):
        """主函数"""
        try:
            # 登录
            nickname = self.login()
            # 签到
            self.checkin()
            # 获取打印等级信息,同时获取当前已听歌曲数
            nowPlayCountOld = self.levelInfoLog()
            # 实时听歌数
            nowPlayCountNew = nowPlayCountOld
            # 已提交次数
            finishNum = 0
            # 刷歌数量没有达到300首并且刷歌次数没有达到设定最大次数则一直刷
            while (finishNum<self.cyclesNumMax and nowPlayCountNew-nowPlayCountOld<300):
                # 刷歌
                fakeSongRes = self.fakeSong()
                if finishNum == 0:
                    # 第一次刷歌打印一下总共的日推歌曲数量
                    print('日推待刷歌数量 %d'%(len(self.songIds)))
                print('听歌信息回传反馈信息:', fakeSongRes)
                # 当前等级信息
                levelInfo = self.levelInfoInWeapi()
                levelData = levelInfo['data']
                if levelData:
                    # 实时听歌信息
                    nowPlayCountNew = levelData['nowPlayCount']
                # 刷歌次数加一
                finishNum += 1
            print('日推待刷歌数量 %d'%(len(self.songIds)))
            self.levelInfoLog()
            # 保存cookies
            self.saveCookie()
        except Exception as e:
            print('异常: %s'%(str(e)))
            self.serverChain('网易云刷歌异常', desp='时间: %s\r\n\r\n信息: %s'%(self.nowWithSep(), str(e)))

    ############################## 歌曲数据部分 start ##############################
    def fakeSong(self):
        """刷歌,模拟听歌 """
        # 获取听歌记录中的歌曲数据
        if not self.songRecords:
            # 获取听歌记录
            self.playRecord()
        # 是否已经获取到了待刷歌歌曲
        if not self.songIds:
            # 获取日推中所有歌曲
            self.getSongIds()
        # 从歌曲ID中去除已经听过的歌
        self.songIdsDeduplicat()
        # 拼接听歌数据回传
        return self.songFeedbackInWeapi()

    def songFeedbackInWeapi(self):
        """根据提供的歌曲ID拼接听歌信息回传网易云音乐服务器，实现模拟听歌
            每次回传 self.songNum 首歌曲的id,最多回传 self.cyclesNumMax 次
        -------------------------------------
            返回日志回传接口的响应信息 """
        # 听歌回传信息表单数据
        songInfos = []
        while len(self.songIds) > 0:
            # 随机取出一首歌,降低重复刷歌的情况
            index = random.randint(0, len(self.songIds)-1)
            # 取出该歌曲并将其从歌曲ID列表中删除,降低重复刷歌的情况
            songId = self.songIds.pop(index)
            # 刷歌表单所需歌曲信息
            songInfo = {'action': 'play'}
            songInfo['json'] = {
                'download':0,
                'end':'playend',
                'id':songId,
                'sourceId':'',
                'time':240,
                'type':'song',
                'wifi':0
            }
            songInfos.append(songInfo)
            # 数量达到每次回传歌曲数量要求就结束
            if len(songInfos) >= self.songNum:
                break
        # 转json
        songInfosJson = json.dumps(songInfos)
        # 听歌信息回传api
        feedbackApi = "%s%s"%(self.feedbackWeapi, self.getCsrf())
        # 加密回传表单
        feedbackForm = self.initFormData({'logs': songInfosJson})
        # 回传数据
        res = self.httpSession.post(feedbackApi, data=feedbackForm, verify=self.verifySSL)
        # 本次听歌ID
        #print('本次听歌ID =', songIdsTing)
        # 成功报文格式 {'code': 200, 'data': 'success', 'message': ''}
        return res.json()

    def songIdsDeduplicat(self):
        """待刷歌曲id去重,去除听歌记录中已经存在的歌曲ID"""
        # 去重
        songIdIntersection = [songId for songId in self.songIds if songId not in self.songRecords]
        # 保存
        self.songIds = songIdIntersection
        return songIdIntersection

    def getSongIds(self):
        """获取待刷歌曲,包括每日推荐歌曲和每日推荐歌单中的歌曲"""
        # 获取日推歌单中的歌曲
        self.playListSongIdsInWeapi()
        # 获取日推歌曲
        self.dailySongIdsInApi()
        return self.songIds

    def playRecord(self):
        """获取听歌记录,所有时间和最近一周都只能获取100首,并且有可能有重复数据"""
        print('开始获取听歌记录...')
        songRecords = []
        if self.accountAccount:
            userId = self.accountAccount['id']
        elif self.accountProfile:
            userId = self.accountProfile['userId']
        else:
            # 没有获取到账户id,直接返回空
            return songRecords
        # 获取听歌记录表单
        recordForm = {'uid': userId, 'type': '-1', 'limit': '1000', 'offset': '0', 'total': 'true', 'csrf_token': self.getCsrf()}
        # 表单加密
        recordFormFinal = self.initFormData(recordForm)
        # 获取听歌记录接口地址
        songRecordWeapi = "%s%s"%(self.songRecordWeapi, self.getCsrf())
        # 发送请求
        res = self.httpSession.post(songRecordWeapi,data=recordFormFinal,verify=self.verifySSL)
        songRecordJson = res.json()
        # 所有时间的听歌记录
        allDataJson = songRecordJson['allData']
        if allDataJson:
            for allDataOne in allDataJson:
                songRecords.append(allDataOne['song']['id'])
        # 最近一周的听歌记录
        weekDataJson = songRecordJson['weekData']
        if allDataJson:
            for weekDataOne in weekDataJson:
                songRecords.append(weekDataOne['song']['id'])
        songRecords = list(set(songRecords))
        # 保存
        self.songRecords = songRecords
        return songRecords

    def dailySongIdsInApi(self):
        """获取每日个性推荐歌曲id"""
        print('开始获取日推歌曲...')
        dailySongIds = []
        # 调用个性推荐歌曲接口
        res = self.httpSession.get(self.dailySongApi, verify=self.verifySSL)
        # 获取所有个性推荐歌曲
        dailySongJsonArr = res.json()['recommend']
        # 遍历获取歌曲id
        for dailySongJson in dailySongJsonArr:
            dailySongIds.append(dailySongJson['id'])
        # 合并可能存在的其他途径获取的歌曲ID
        dailySongIds.extend(self.songIds)
        # 歌曲ID去重
        dailySongIds = list(set(dailySongIds))
        # 保存
        self.songIds = dailySongIds
        return self.songIds

    def playListSongIdsInWeapi(self):
        """根据歌单ID获取歌单中歌曲ID """
        # 获取热门推荐歌曲
        self.playListInMobile() if self.isGetPopular else None
        # 获取日推歌单
        self.playListInWeapi()
        print('开始获取日推歌单中的歌曲...')
        songIds = []
        # 遍历歌单信息
        for playlistId in self.playlistIds:
            # 获取歌单信息所需表单
            songIdsForm = {'id': playlistId, 'n': 1000, 'csrf_token': self.getCsrf()}
            # 加密获取最终表单
            songIdsFormFinal = self.initFormData(songIdsForm)
            # 获取歌单中歌曲信息
            api = "%s%s"%(self.playlistInfoWeapi, self.getCsrf())
            res = self.httpSession.post(api, data=songIdsFormFinal, verify=self.verifySSL)
            playlistDetailJson = res.json()
            # 获取当前歌单所有歌曲
            songsJson = playlistDetailJson['playlist']['trackIds']
            # 遍历获取歌曲id
            for songJson in songsJson:
                songIds.append(songJson['id'])
        # 合并可能存在的其他途径获取的歌曲ID
        songIds.extend(self.songIds)
        # 歌曲ID去重
        songIds = list(set(songIds))
        # 保存
        self.songIds = songIds
        return self.songIds

    def playListInWeapi(self):
        """通过接口获取每日个性推荐歌单ID"""
        print('开始获取个性日推歌单...')
        # 获取个性推荐歌单id的表单
        playListForm = {'csrf_token': self.getCsrf()}
        # 加密表单
        playListFormFinal = self.initFormData(playListForm)
        # 获取推荐歌单
        res = self.httpSession.post(self.playListWeapi, data=playListFormFinal, verify=self.verifySSL)
        # 转json
        playlistJson = res.json()
        # 获取所有歌单
        playlists = playlistJson['recommend']
        playlistIds = []
        # 遍历歌单获取歌单的ID
        for playlist in playlists:
            playlistIds.append(playlist['id'])
        # 合并可能存在的其他途径获取的歌单ID
        playlistIds.extend(self.playlistIds)
        # 歌单ID去重
        playlistIds = list(set(playlistIds))
        # 保存
        self.playlistIds = playlistIds
        return playlistIds

    def playListInMobile(self):
        """通过移动端首页获取热门推荐歌单ID"""
        print('开始获取移动端热门推荐歌单...')
        playListIds = []
        # 访问移动版首页获取推荐歌单
        res = self.httpSession.get(self.mobileIndex, headers={'User-Agent': self.userAgentMobile})
        bsoup = BeautifulSoup(res.text, 'html.parser')
        # 获取设置歌单的就是部分
        scriptSoup = bsoup.select_one('body script')
        if scriptSoup:
            # 获取js代码
            js = scriptSoup.string.strip()
            # 执行js,获取数据
            playListJson = js2py.eval_js(js)
            # 主要数据
            homeJson = playListJson['Home']
            if homeJson:
                if homeJson['code'] == 200:
                    # 推荐歌单数据
                    playListJson = homeJson['result']
                    # 遍历提取歌单ID
                    for playList in playListJson:
                        playListIds.append(playList['id'])
                    # 合并可能存在的其他途径获取的歌单ID
                    playListIds.extend(self.playlistIds)
                    # 歌单ID去重
                    playListIds = list(set(playListIds))
                    # 保存
                    self.playlistIds = playListIds
                    print(playListIds)
                    return playListIds
        print('移动端推荐歌单获取失败')
        return playListIds

    def getCsrf(self):
        """获取__csrf,若未获取过从cookies中获取并保存到self.csrf中"""
        if not self.csrf:
            # 从cookies中提取csrf
            cookies = self.httpSession.cookies.items()
            for cook in cookies:
                if cook[0] == '__csrf':
                    self.csrf = cook[1]
                    break
        return self.csrf
    ############################### 歌曲数据部分 end ###############################

    ############################## 签到部分 start ##############################
    def checkin(self):
        """签到"""
        # 判断是否可以签到
        if self.couldCheckin():
            print('签到结果:', self.checkinInWeapi())

    def couldCheckin(self):
        """是否已签到"""
        # 访问首页
        res = self.httpSession.get(self.dataIndex)
        # 解析html
        bsoup = BeautifulSoup(res.text, 'html.parser')
        # 寻找签到部分
        checkinSoup = bsoup.select_one('div.n-user-profile div.f-cb div.info > div')
        if checkinSoup:
            # 签到信息
            checkinText = checkinSoup.get_text().strip()
            if checkinText == '已签到':
                print('今日已经签到,无需签到')
                return False
            elif checkinText == '签到':
                print('今日未签到,需要签到')
                return True
        print('签到状态未知,尝试签到')
        return True

    def checkinInWeapi(self):
        """签到"""
        checkinForm = {'type': 1}
        # 最终签到表单
        checkinFormFinal = self.initFormData(checkinForm)
        # 签到
        res = self.httpSession.post(self.checkinWeapi,data=checkinFormFinal,verify=self.verifySSL)
        return res.json()
    ############################### 签到部分 end ###############################

    ############################## 登录部分 start ##############################
    def levelInfoLog(self):
        """获取打印解析账号等级信息"""
        # 获取等级信息
        levelInfoMsg = self.levelInfoInWeapi()
        # 等级数据
        levelData = levelInfoMsg['data']
        if levelData:
            # 当前听歌数量
            nowPlayCount = levelData['nowPlayCount']
            print("现有等级:%d; 当前等级已听歌曲%d首,还需听%d首; 已登录%d天,还需登录%d天"%(levelData['level'],
                        levelData['nowPlayCount'],levelData['nextPlayCount']-levelData['nowPlayCount'],
                        levelData['nowLoginCount'],levelData['nextLoginCount']-levelData['nowLoginCount']))
            return nowPlayCount
        return 0

    def levelInfoInApi(self):
        """获取账号等级信息"""
        res = self.httpSession.get(self.levelApi, verify=self.verifySSL)
        return res.json()

    def levelInfoInWeapi(self):
        """获取账号等级信息"""
        # 获取账号等级信息数据表单
        levelForm = {'csrf_token': self.getCsrf()}
        # 表单加密
        levelFormFinal = self.initFormData(levelForm)
        # 获取等级信息
        res = self.httpSession.post(self.levelWeapi, data=levelFormFinal, verify=self.verifySSL)
        return res.json()

    def accountInfoInApi(self):
        """获取账号信息"""
        # self.accountApi 不需要提交表单,直接get请求即可
        res = self.httpSession.get(self.accountApi, verify=self.verifySSL)
        return res.json()

    def isLogin(self):
        """通过获取账号信息,判断是否登录成功
        -------------------------------------
            登录成功返回账号昵称,失败返回None """
        # 获取账号信息
        accountInfo = self.accountInfoInApi()
        account = accountInfo['account']
        if account:
            self.accountAccount = account
        profile = accountInfo['profile']
        if profile:
            self.accountProfile = profile
            return profile['nickname']
        return None

    def login(self):
        """登录,首先尝试读取cookieJar,失败后读取cookieStr,失败后用户名密码登录"""
        nickname = None
        # 使用cookieJar登录
        self.loginWithCookieJar()
        # 判断是否登录成功
        nickname = self.isLogin()
        if not nickname:
            print('更新cookieJar登录失败')
            # 未登录,尝试读取cookieStr登录
            self.loginWithCookieStr()
            # 判断是否登录成功
            nickname = self.isLogin()
            if not nickname:
                print('更新cookieStr登录失败')
                # 未登录,使用用户名密码登录
                nickname = self.loginWithPwdInWeapi()
                if not nickname:
                    raise Exception('登录失败')
        print('网易云 <%s> 登录成功'%(nickname))
        # 更新本地cookies
        self.saveCookie()
        return nickname

    def loginWithPwdInWeapi(self):
        """使用用户名密码登录,只支持手机号
        -------------------------------------
            登录成功返回账号昵称,失败返回None """
        print('使用用户名密码登录...')
        # 登录表单
        loginForm = {
            "phone": self.username,
            "countrycode": self.countryCode,
            # 对密码进行MD5加密
            "password": self.md5(self.password),
            "rememberLogin": "true"
        }
        # 加密登录表单
        loginFormFinal = self.initFormData(loginForm)
        # 提交登录请求
        res = self.httpSession.post(self.loginPhoneWeapi, data=loginFormFinal, verify=self.verifySSL)
        # 转json
        resultJson = res.json()
        if (resultJson['code'] == 200):
            # 昵称
            nickname = None
            # 获取返回结果中的nickname
            if resultJson:
                # 账户信息
                account = resultJson['account']
                if account:
                    self.accountAccount = account
                # 个人账号信息
                # account 和 profile 内容有重合部分
                profile = resultJson['profile']
                if profile:
                    self.accountProfile = profile
                    nickname = profile['nickname']
                    # 登录成功保存cookies
                    self.saveCookie()
            return nickname
        else:
            raise Exception('登录失败: %s'%resultJson)

    def loginWithCookieStr(self):
        """通过读取本地保存的cookie文件获取cookie尝试登录
        -------------------------------------
            更新了cookie返回True,否则返回False"""
        print('更新cookieStr登录...')
        cookieDict = self.readCookieStr()
        if cookieDict:
            # 清空cookieJar防止干扰
            self.httpSession.cookies.clear()
            # 更新cookies
            self.httpSession.cookies.update(cookieDict)
            return True
        return False

    def loginWithCookieJar(self):
        """通过读取本地保存的cookieJar文件获取cookieJar尝试登录
        -------------------------------------
            更新了cookieJar返回True,否则返回False"""
        print('更新cookieJar登录...')
        cookieJar = self.readCookieJar()
        if cookieJar:
            # 更新cookies
            self.httpSession.cookies = cookieJar
            return True
        return False
    ############################### 登录部分 end ###############################

    ############################## cookies持久化部分 start ##############################
    def saveCookie(self):
        """保存cookies,cookies字典转成的字符串和requests.session().cookies对象"""
        # cookieJar持久化
        self.saveCookieJar()
        # cookies字符串持久化
        self.saveCookieStr()

    def readCookieJar(self):
        """从文件读取持久化后的cookiesJar,即requests.cookies或者requests.session().cookies
        -------------------------------------
            返回反持久化后的cookiesjar """
        if os.path.exists(self.cookieJarPath):
            try:
                # 读取文件
                with open(self.cookieJarPath, mode='rb') as f:
                    # 读取
                    cookieJar = pickle.load(f)
                return cookieJar
            except Exception as e:
                # 数据为空
                print('cookieJar持久化文件可能是空文件')
                return None
        else:
            with open(self.cookieJarPath, mode='wb') as f:
                print('cookieJar持久化文件不存在,自动创建')
            return None

    def saveCookieJar(self):
        """将cookiesJar持久化到文件,完整保存cookies"""
        # 写入文件
        with open(self.cookieJarPath, mode="wb") as f:
            pickle.dump(self.httpSession.cookies, f)
            print('最新cookiesJar已保存')

    def readCookieStr(self):
        """从文件读取cookies字符串并转成字典
        -------------------------------------
            返回字典类型的cookies """
        cookiesDict = {}
        if os.path.exists(self.cookieStrPath):
            # 读取文件,不存在则自动创建
            with open(self.cookieStrPath, mode='r', encoding="utf-8") as f:
                cookieStr = f.read()
            # 转为字典
            if cookieStr:
                # 分割字符串
                cookiesTuple = cookieStr.strip().split(';')
                # 遍历
                for cookie in cookiesTuple:
                    # 分割单个cookie
                    cookieTuple = cookie.split('=')
                    # 保存到字典中
                    cookiesDict[cookieTuple[0].strip()] = cookieTuple[1].strip() if len(cookieTuple)>1 else ''
        else:
            with open(self.cookieStrPath, mode="w", encoding="utf-8") as f:
                print('cookieStr文件不存在,自动创建')
        return cookiesDict

    def saveCookieStr(self):
        """将cookies转为字符串并写入文件,方便手动提供cookies"""
        # 遍历cookies拼接成字符串
        cookieStr = ''
        for key, val in self.httpSession.cookies.items():
            cookieStr = "%s%s=%s;"%(cookieStr, key.strip(), val.strip())
        # 去除两边的分号
        cookieStr = cookieStr.strip(';')
        # 写入文件
        with open(self.cookieStrPath, mode="w", encoding="utf-8") as f:
            f.write(cookieStr)
            print('最新cookies字符串已保存')
    ############################### cookies持久化部分 end ###############################

    ############################## 数据加密部分 start ##############################
    def initFormData(self, formData):
        """对提交的表单数据进行加密
            连续进行两次AES加密,第一次加密密钥为固定值,第二次加密密钥为随机16位字符串
                初始化向量 固定值 = '0102030405060708'
                第一次AES加密密钥 固定值 = '0CoJUm6Qyw8W8jud' 对 ["爱心", "女孩", "惊恐", "大笑"] 列表进行加密
                第二次加密密钥为随机16位字符串
            具体计算方法在 https://s3.music.126.net/web/s/core_xxx.js 中 
        ----------------------------
            formData: 要提交的表单数据
        ----------------------------
            返回二次AES加密后的表单数据和RSA加密后的二次AES加密密钥 """
        # 转json
        formDataJsonStr = json.dumps(formData)
        # 第一次AES加密
        formDataAes = self.aesEncrypt(self.aesNonce, self.aesIV, formDataJsonStr)
        # 获取第二次AES加密密钥
        aesKey = self.createAESkey()
        # 第二次AES加密
        formDataAes = self.aesEncrypt(aesKey, self.aesIV, formDataAes)
        # 将密钥进行RSA加密
        encryptedAESKey = self.rsaEncrypt(self.rsaPubkey, self.modulus, aesKey)
        # 加密完毕的表单
        formDataFinal = {'params': formDataAes, 'encSecKey': encryptedAESKey}
        return formDataFinal

    def createAESkey(self):
        """获取一个a-zA-Z0-9范围内的16位随机字符串,用来对表单进行二次AES加密
        ----------------------------
            返回一个16位随机字符串 范围a-zA-Z0-9 """
        return ''.join(random.sample(string.ascii_letters + string.digits, 16))

    def pkcs7Padding(self, content):
        """对明文进行16位补全,使其bytes数组位数达到16位的倍数,本来就是16倍数的也会被再补16位
            在原始数据向后补
        ----------------------------
            content: 明文
        ----------------------------
            返回位数补齐之后的明文 """
        # 明文的bytes长度
        bytesLen = len(bytes(content, encoding='UTF-8'))
        # 需要补齐的位数
        padLen = AES.block_size - (bytesLen % AES.block_size)
        # 补齐的数据,使用 chr(padLen) 来补齐,补了 padLen 位
        padContent = chr(padLen) * padLen
        # 补齐
        return content + padContent

    def pkcs7Unpadding(self, paddedContent):
        """去除被填充过得数据得到原始数据
        ----------------------------
            paddedContent: 填充过得数据
        ----------------------------
            返回原始数据 """
        # 数组总位数
        contentLen = len(paddedContent)
        # 在数据最后填充过得数据,即最后一位
        padContent = paddedContent[contentLen-1]
        # 去除补足的数据 原始数据补的位数
        return paddedContent[:contentLen-ord(padContent)]

    def aesEncrypt(self, secKey, iv, content):
        """对数据进行CBC模式的AES加密,用来加密表单数据
        ----------------------------
            secKey: 加密密钥
            iv: 初始偏移量
            content: 要被加密的数据
        ----------------------------
            返回CBC模式AES加密后的数据 """
        # 创建一个CBC模式的 cipher
        cipher = AES.new(bytes(secKey, 'UTF-8'), AES.MODE_CBC, bytes(iv, 'UTF-8'))
        # 对数据进行位数补足
        paddedContent = self.pkcs7Padding(content)
        # 进行AES加密
        encryptedContent = cipher.encrypt(bytes(paddedContent, 'UTF-8'))
        #print('base64编码后:', base64.b64encode(encryptedContent))
        # 重新编码为字符串
        return str(base64.b64encode(encryptedContent), 'utf-8')

    def aesDecrypt(self, secKey, iv, encryptedContent):
        """对进行CBC模式的AES加密的数据进行解密
        ----------------------------
            secKey: 加密密钥
            iv: 初始偏移量
            encryptedContent: 被加密过的数据
        ----------------------------
            返回解密后的数据 """
        # 创建一个CBC模式的 cipher
        cipher = AES.new(bytes(secKey, 'UTF-8'), AES.MODE_CBC, bytes(iv, 'UTF-8'))
        # 对密文进行base64解码
        encryptedBytes = base64.b64decode(bytes(encryptedContent, 'UTF-8'))
        # AES解密
        decryptedBytes = cipher.decrypt(encryptedBytes)
        # 重新编码为字符串
        decryptedContent = str(decryptedBytes, 'UTF-8')
        # 去除填充内容
        return self.pkcs7Unpadding(decryptedContent)

    def rsaEncrypt(self, pubKey, modulus, content):
        """RSA加密,用来对表单二次AES加密密钥进行加密
            网易云音乐的加密采用非常规填充方式,不是PKCS1和PKCS1_OAEP,网易的做法是直接向前补0
            这样加密出来的密文有个特点: 加密过程没有随机因素,明文多次加密后得到的密文是相同的
            因此 表单二次AES加密密钥可以写固定值,该密钥的RSA加密密文也是固定值
        ----------------------------
            pubKey: RSA加密公钥
            modulus: 模数, 用来对原始数据取模
            content: 需要加密的数据
        ----------------------------
            返回RSA加密后的数据 """
        # 明文进行反序
        content = content[::-1]
        # 原始数据与公钥进行幂运算
        content = int(codecs.encode(content.encode('utf-8'),'hex'),16) ** int(pubKey,16)
        # 取模
        remainder = content % int(modulus, 16)
        # 转换为256位十六进制字符串 密文字符串右对齐,前面填充0
        return format(remainder, 'x').zfill(256)

    def md5(self, content):
        """对数据进行md5加密
        ----------------------------
            content: 需要加密的字符串
        ----------------------------
            返回原始数据的md5值 """
        md5Hash = hashlib.md5()
        # 数据转bytes
        md5Hash.update(bytes(content, encoding='utf-8'))
        # 转十六进制
        return md5Hash.hexdigest()
    ############################### 数据加密部分 end ###############################

    def nowWithSep(self):
        """获取当前时间字符串,有分隔符 年年年年-月月-日日 时时:分分:秒秒; 东八区24小时制 """
        return datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")

    def serverChain(self, text, desp=None):
        """调用server酱发送消息
        ----------------------------
            text: 要发送的消息标题
            desp: 要发送的消息正文 """
        if not self.serverChainKey:
            print('未设置server酱密钥(serverChainKey参数),将不通过server酱发送信息')
            return
        if text:
            # 拼接标题
            msg = '?text=%s'%(quote(text))
            if desp:
                # 拼接正文
                msg = '%s&desp=%s'%(msg, quote(desp))
            # 拼接密钥
            serverUrl = 'https://sc.ftqq.com/%s.send%s'%(self.serverChainKey, msg)
            # 发送请求
            requests.head(serverUrl).close()
        else:
            print('server酱 消息标题 text 参数不能为空')


if __name__ == '__main__':
    main()
