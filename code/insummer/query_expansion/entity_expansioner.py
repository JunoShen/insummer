#!/usr/bin/python3

'''
说明:这个文件是查询扩展类,主要负责查询扩展方面的工作
'''
import math
import sys
from abc import ABCMeta, abstractmethod
from ..common_type import Question
from ..util import NLP
from .entity_finder import NgramEntityFinder
from ..knowledge_base.entity_lookup import InsunnetEntityLookup
from ..knowledge_base import concept_tool

from ..ranker import Pageranker,Hitsranker,CCRanker,KCoreRanker

nlp = NLP()
searcher = InsunnetEntityLookup()

import networkx as nx
import itertools
from operator import itemgetter

import time
clock = time.time

#定义抽象类
#这个类是实体扩展的类,主要功能是
#1.给定question, 对其进行实体扩展
#2.将title扩展的实体与answer相比较
#3.能够换用不同的策略进行扩展

class abstract_entity_expansioner(metaclass=ABCMeta):
    def __init__(self,mquestion,entity_finder,display=False):
        assert mquestion.type_name == "Question"

        self.__question = mquestion

        #这个包含的是每个句子中的实体和句子
        #基本结构是[ (sentence(without tokenize) , [entity]  ) ]
        self.__sentence_entity = []

        #这个是所有句子中所有的实体
        self.__sentence_total_entity = set([])

        self.__expand_entity = None

        self.__entity_finder = entity_finder

        self.display = display

    #返回问题题目
    def get_title(self):
        return self.__question.get_title()

    #返回整个问题
    def get_question(self):
        return self.__question

    #返回答案
    def get_answers(self):
        return self.__question.get_nbest()

    #给句子实体对增加句子实体对
    def append_sentence_entity(self,se_pair):
        self.__sentence_entity.append(se_pair)

    #得到实体的答案全部实体
    def get_sentence_total_entity(self):
        return self.__sentence_total_entity

    #得到句子实体
    def get_sentence_entity(self):
        return self.__sentence_entity    

    #构建sentence entity
    def construct_sentence_entity(self):
        #先把所有answer取出来
        answers = self.get_answers()

        #对于每一个答案
        for answer in answers:

            #得到答案的内容
            content = answer.get_content()

            sentences = nlp.sent_tokenize(content)

            #对于每一个句子
            for sentence in sentences:

                #实体链接
                finder = NgramEntityFinder(sentence)

                #找出所有实体
                entity = finder.extract_entity(display=False)

                #跟总实体取并
                self.__sentence_total_entity = self.__sentence_total_entity.union(set(entity))

                #加入结果集中
                if len(entity) >0 :
                    self.append_sentence_entity((sentence,entity))

    #得到标题的实体
    def title_entity(self):
        title = self.get_title()

        #去掉多余实体,这些实体明显具有讨论的意味，认为是没有表义性质的
        remove = {"discuss","describe","specify","explain","identify","include","involve","note"}

        #基实体集初始化
        base_entity = set()

        #先抽取问题的实体
        sentences = nlp.sent_tokenize(title)
        for sentence in sentences:
            finder = self.__entity_finder(sentence)
            entity = finder.extract_entity()
            if len(entity) > 0:
                base_entity = base_entity.union(set(entity))


        base_entity = base_entity.difference(remove)
        return base_entity

    def print_sentence_entity(self):
        for sentence,entity in self.__sentence_entity:
            print("%s\n%s\n%s"%(sentence,entity,100*"="))
            
    #主体调用的函数
    #先把句子中所有的实体都抽出来
    #再进行实体扩展, 然后进行评价
    def run(self):
        #抽取答案句子中的所有实体
        self.construct_sentence_entity()

        #扩展实体
        expand_terms = self.expand()

    #抽象方法, title扩展类, 用于扩展实体, 每个类必须定义该方法
    #也就是算法的精华部分, 最后会输出扩展的实体
    @abstractmethod
    def expand(self):
        pass

        
#现阶段的层次过滤方式，这个是可以继承的，非常好用
#level1 是同义层层数
#level2 是关联层层数
class level_filter_entity_expansioner(abstract_entity_expansioner):
    def __init__(self,mquestion,entity_finder,level1,level2,display):
        abstract_entity_expansioner.__init__(self,mquestion,entity_finder,display)
        self.level1 = level1
        self.level2 = level2

        #经过同义层过滤后的实体个数
        self.syn_filter_len = -1 

    def get_level(self):
        return self.level1,self.level2
        
    #这个是扩展的通用方法, 给定输入的base_entity集合, 利用某种扩展规则进行扩展, 还有扩展层数
    #返回扩展的实体    
    def expand_with_entity_type(self,base_entity,expand_rule,expand_level):

        #开始扩展
        #算法流程打算用基于栈的非递归方法
        
        #1. 记录当前的实体数量
        previous_entity_length = len(base_entity)

        #2. expand_entity初始化设为base_entity
        expand_entity = base_entity.copy()

        #3. 假设扩展之前 a,b,c 当a,b,c 都扩展完之后, 需要与之前的比较大小, 那么之前的需要初始化进行记录
        previous_expand_entity = expand_entity.copy()

        #4. 判断条件, 1. expand_entity 的体积没有增长, 2.previous_expand_entity 已经遍历完了
        indx = 0

        while indx < expand_level:

            #对每个前一轮的实体来说
            for entity in previous_expand_entity:
                #进行同义词扩展
                temp_expand_entity = expand_rule(entity)

                #合并
                expand_entity = expand_entity.union(temp_expand_entity)
                
            indx += 1    
            #扩展的集合体积没有增长, 则说明循环结束, 跳出循环, 如不然则重新赋值
            if len(expand_entity) == previous_expand_entity:
                break;
            else:
                previous_entity_length = len(expand_entity)
                previous_expand_entity = expand_entity.copy()

        return expand_entity


    #这个函数的作用是,给定带有weight的基实体, 返回其他的基实体, 是具有如下形式, {expand1:{base1:weight1,base2:weight2}...}
    def expand_with_entity_weight(self,entity_dict,expand_rule):
        target_dict = {}

        #对于基实体的每个实体来说
        for entity in entity_dict:
            #得到的是一个(邻居,权值)的list
            neighbour_weight = expand_rule(entity)

            #反向建立一个target的字典里面存储的都是base entity 和weight, 暂定为tuple
            for neighbour,nweight in neighbour_weight:
                target_dict.setdefault(neighbour,[])
                target_dict[neighbour].append( (entity,nweight) )

        return target_dict
        

    #==================下面的是接口方法======================
    #expand的具体方法
    def expand(self):

        #step1: 得到base entity(title的所有实体)
        base_entity = self.title_entity()

        #step2: 同义层扩展
        syn_entity = self.syn_expand(base_entity)

        #step3: 同义层过滤
        syn_entity = self.syn_filter(syn_entity)
        self.syn_filter_len = len(syn_entity)

        #step4: 关联层扩展
        relate_entity = self.relate_expand(syn_entity)

        
        return relate_entity
        
    def syn_expand(self,base_entity):
        expand_rule = searcher.synonym_entity
        result = self.expand_with_entity_type(base_entity,expand_rule,self.level1)
        return result
        
    #如果你啥也不写就是啥也不过滤
    def syn_filter(self,entity):
        return entity

    #关联层扩展, 这个默认也不实现, 因为在后面做的时候应该是和filter做到一起的
    def relate_expand(self,entity):
        return entity

    #定义关联曾的filter的接口
    #entity是单独的一个实体
    #base_entity 是现有的基实体 
    @abstractmethod
    def relate_filter(self,base_entity,entity):
        pass
        
    #=====================================================
        
#这个算法只扩展同义词类
class OnlySynExpansioner(level_filter_entity_expansioner):
    #max level是可扩展到最大层数, 如需要两层 则level = 2
    def __init__(self,mquestion,entity_finder,level,display):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level,level,display)

    def relate_filter(self,base_entity,entity):
        pass

#这个方法先扩展成同义词然后扩展关联关系
class SynRelateExpansioner(level_filter_entity_expansioner):
    def __init__(self,mquestion,entity_finder,level1,level2,display):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entity_type(entity,expand_rule,level2)
        
        return result

    def relate_filter(self,base_entity,entity):
        pass

#===========================================
#获得两个实体之间的权重
#第一个函数与第二个函数的区别是
#第一个函数只有相同实体才是0,1, 剩下的都是按照正常的来
#第二个函数只要有连接就是1,剩下的是0
cn = concept_tool()
def get_weight1(ent1,ent2):
    weight = cn.entity_strength(ent1,ent2)
    if ent1 == ent2 :
        return 1
    else:
        return weight

def get_weight2(ent1,ent2):
    weight = cn.entity_strength(ent1,ent2)
    if ent1 == ent2 or weight != 0:
        return 1
    else:
        return 0

#============================================


#这个方法先扩同义词, 然后用rank(page rank 或者hits)
class SynPagerankExpansioner(level_filter_entity_expansioner):

    #n是同义词过滤实体后的个数
    def __init__(self,mquestion,entity_finder,level1,level2,display,n=30):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)
        self.n = n


    #=======================重写部分================================
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 10:
            return base_entity

        ranker = Pageranker(base_entity)
        result = ranker.rank()    
            
        important_entity = result
        #先求最小索引
        l = min(len(important_entity),self.n)
        
        #得到top n, 并且并上基实体
        topn = set(important_entity[:l]).union(self.title_entity())

        return topn

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entity_type(entity,expand_rule,level2)
        
        return result
        
    #重现
    def relate_filter(self,base_entity,entity):
        pass

    #==============================================================
        

    def hits(self,gr):
        h,a = nx.hits(gr,max_iter = 300)
        return h
        
#这个方法先扩同义词, 然后用rank(page rank 或者hits)
class SynHitsExpansioner(level_filter_entity_expansioner):

    #n是同义词过滤实体后的个数
    def __init__(self,mquestion,entity_finder,level1,level2,display,n=20):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)
        self.n = n


    #=======================重写部分================================
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 10:
            return base_entity

        ranker = Hitsranker(base_entity)
        result = ranker.rank()    
            
        important_entity = result
        #先求最小索引
        l = min(len(important_entity),self.n)
        
        #得到top n, 并且并上基实体
        topn = set(important_entity[:l]).union(self.title_entity())

        return topn

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entity_type(entity,expand_rule,level2)
        
        return result
        
    #重现
    def relate_filter(self,base_entity,entity):
        pass

    #==============================================================
        

    def hits(self,gr):
        h,a = nx.hits(gr,max_iter = 300)
        return h        


#这个方法先扩同义词, 然后根据联通分量过滤或者度进行过滤
class SynCCExpansioner(level_filter_entity_expansioner):
    
    def __init__(self,mquestion,entity_finder,level1,level2,display):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)

    #=======================重写部分================================
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 10:
            return base_entity

        ranker = CCRanker(base_entity)
        result = ranker.rank()    
            
        
        important_entity = result.union(self.title_entity())

        return important_entity

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entity_type(entity,expand_rule,level2)
        
        return result
        
    #重现
    def relate_filter(self,base_entity,entity):
        pass

    #==============================================================
        
#这个方法先扩同义词, 然后根据联通分量过滤或者度进行过滤
class SynKCoreExpansioner(level_filter_entity_expansioner):
    
    def __init__(self,mquestion,entity_finder,level1,level2,display):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)

    #=======================重写部分================================
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 10:
            return base_entity

        ranker = KCoreRanker(base_entity)
        result = ranker.rank()    
        
        important_entity = result.union(self.title_entity())

        return important_entity

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entity_type(entity,expand_rule,level2)
        
        return result
        
    #重现
    def relate_filter(self,base_entity,entity):
        pass

    #==============================================================
        

#过滤关联层为主        
class RankRelateFilterExpansioner(SynPagerankExpansioner):
    def __init__(self,mquestion,entity_finder,level1,level2,display,n=30,length=8000):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)
        self.n = n
        self.count = 0
        self.length = length

    #=======================重写部分================================
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 0:
            return base_entity #...这里实现的有问题，这里的字典没有加权值

        ranker = Pageranker(base_entity)
        result = ranker.rank(return_type='dict')
        
        important_entity = result
        #先求最小索引
        l = min(len(important_entity),self.n)

        #得到top n, 并且并上基实体,注意, 这里返回的形式是dict, 所以后面加上了这么多东西
        topn = important_entity[:l]

        title_entity = self.title_entity()

        for indx in range(l+1,len(important_entity)):
            enti,weig = important_entity[indx]
            if enti in title_entity:
                topn.append((enti,weig))

        topn = dict(topn)

        self.syn_entity_weight = topn

        return topn

    
    #重载relate_expand
    #这个是我想要的非并行化的扩展方法, 还在弄
    #entity_dict 是一个带权重的实体集
    def relate_expand(self,entity_dict):

        expand_rule = searcher.relate_entity_weight
        
        target_dict = self.expand_with_entity_weight(entity_dict,expand_rule)
        
        result = self.relate_filter(target_dict,entity_dict)

        #result = result.union(self.title_entity())
                
        return result
        
    def relate_filter(self,expand_entity,base_entity):

        result = {}
        #对于每一个需要判别的实体来说
        for entity in expand_entity:

            #得到每个实体和基实体之间的关系
            base_weight = expand_entity[entity]

            #conn_with_base 是与基实体联系的强弱
            conn_with_base = 0
            for ent,weight in base_weight:
                conn_with_base += base_entity[ent] * weight

            
            result[entity] = (conn_with_base) * ( (len(base_weight) + 1)**2 ) 


        result = sorted(result.items(),key=lambda d:d[1],reverse=True)

        result = result[:self.length]

        total_entity = self.get_sentence_total_entity()
        
        return result
        
    
    #--------重构版-----------
    def run(self):
        #抽取答案句子中的所有实体
        self.construct_sentence_entity()

        #扩展实体
        expand_terms = self.expand()

        #评价,这个还没有弄
        return expand_terms
