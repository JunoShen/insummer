#!/usr/bin/python3
#coding=utf-8

import re
import pickle
import sys
from bs4 import BeautifulSoup
sys.path.append("..")
import insummer
from insummer.common_type import Question,Answer
from insummer.read_conf import config

#获得duc文档路径和最后question.pkl存放路径
duc_conf = config('../../conf/question.conf')

#将某一具体的文档处理成单个答案
def doc_to_answer(doc_path):
    answer_re = re.compile(r'''<TEXT>(.+?)</TEXT>''',re.DOTALL)
    p_re = re.compile(r'''<P>(.+?)</P>''',re.DOTALL)
    text_str = ''
    with open(doc_path,'r') as infile:
        for line in infile.readlines():
            if line != '\n':
                text_str += line
        infile.close()
    answer_part = answer_re.findall(text_str)[0]
    text_str = BeautifulSoup(answer_part).get_text()
    text_str = text_str.replace("&QL;",'')
    text_str = text_str.replace("&QC;",'')
    text_str = text_str.replace("&UR;",'')
    text_str = text_str.replace("&LR;",'')
    text_str = text_str.replace("-----",'')
    text_str = text_str.replace("----",'')
    return text_str

#根据topic文档，将topic和其对应的文档转换成question和answer
def get_topic(t_path):
    #REs for extract the topic items
    topic_re = re.compile(r'''<topic>(.+?)</topic>''',re.DOTALL)
    num_re = re.compile(r'''<num>(.+?)</num>''',re.DOTALL)
    title_re = re.compile(r'''<title>(.+?)</title>''',re.DOTALL)
    narr_re = re.compile(r'''<narr>(.+?)</narr>''',re.DOTALL)
    doc_re = re.compile(r'''<docs>(.+?)</docs>''',re.DOTALL)

    print("开始读取topic文档...")
    str_list = ''
    with open(t_path['duc_topic'],'r') as infile:
        for line in infile.readlines():
            if line != '\n':
                str_list += line
        infile.close()
    print("开始抽取topic内容...")
    topic_str_list = topic_re.findall(str_list)

    question_list = []
    
    for idx,item in enumerate(topic_str_list):
        #doc_topic_dir:
        #<num> 里标注的就是topic number！
        topic_dir_num = num_re.findall(item)[0].replace(' ','/')
        #question_title:
        topic_title = title_re.findall(item)[0]
        topic_narr = narr_re.findall(item)[0]
        #answer's document
        topic_docs = doc_re.findall(item)[0].split('\n')[1:-1]

        #construct the question:
        question_title = (topic_title[:-1] + '. ' + topic_narr).replace('\n',' ')

        title_author = topic_dir_num

        #construct the answer:
        answer_list = []
        for doc_t in topic_docs:
            doc_path = t_path['duc_main'] + topic_dir_num + doc_t
            answer_author = topic_dir_num + doc_t
            single_answer = doc_to_answer(doc_path)
            answer_list.append(Answer(single_answer,0,0,answer_author))

        question_list.append(Question(question_title,'','',answer_list,title_author,len(answer_list)))
        print(question_list[-1].get_title())

    with open(t_path['duc_question'],'wb') as outfile:
        pickle.dump(question_list,outfile,True)
        outfile.close()
if __name__ == "__main__":
            
    get_topic(duc_conf)
