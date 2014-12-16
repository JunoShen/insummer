#!/usr/bin/python3

'''
说明:这个文件是查询扩展类,主要负责查询扩展方面的工作
'''

import sys
from abc import ABCMeta, abstractmethod
from ..common_type import Question
from ..util import NLP
from .entity_finder import NgramEntityFinder
from ..knowledge_base.entity_lookup import ConceptnetEntityLookup,InsunnetEntityLookup
from ..knowledge_base import concept_tool
from ..evaluation import bias_overlap_ratio,bias_overlap_quantity

nlp = NLP()
searcher = InsunnetEntityLookup()#ConceptnetEntityLookup()

import networkx as nx
import itertools
from operator import itemgetter
import matplotlib.pyplot as plt 

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

    def get_title(self):
        return self.__question.get_title()
        
    def get_question(self):
        return self.__question

    def get_answers(self):
        return self.__question.get_nbest()

    def append_sentence_entity(self,se_pair):
        self.__sentence_entity.append(se_pair)

    def get_sentence_total_entity(self):
        return self.__sentence_total_entity

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

            #sentence tokenize
            sentences = nlp.sent_tokenize(content)

            #对于每一个句子
            for sentence in sentences:

                finder = NgramEntityFinder(sentence)

                #找出所有实体
                entity = finder.extract_entity(display=False)

                #把总实体相加
                self.__sentence_total_entity = self.__sentence_total_entity.union(set(entity))

                #加入结果集中
                if len(entity) >0 :
                    self.append_sentence_entity((sentence,entity))

    #得到标题的实体
    def title_entity(self):
        title = self.get_title()

        #基实体集初始化
        base_entity = set()

        #先抽取问题的实体
        sentences = nlp.sent_tokenize(title)
        for sentence in sentences:
            finder = self.__entity_finder(sentence)
            entity = finder.extract_entity()
            if len(entity) > 0:
                base_entity = base_entity.union(set(entity))

        return base_entity

    def print_sentence_entity(self):
        for sentence,entity in self.__sentence_entity:
            print("%s\n%s\n%s"%(sentence,entity,100*"="))
            
    #各个句子的平均实体数目
    def average_sentence_entity(self):
        #句子数目
        sentence_num = len(self.__sentence_entity)

        entity_num = 0
        for sentence,entity in self.__sentence_entity:
            entity_num += len(entity)

        return entity_num/sentence_num
        
    #主体调用的函数
    #先把句子中所有的实体都抽出来
    #再进行实体扩展, 然后进行评价
    def run(self):
        #抽取答案句子中的所有实体
        self.construct_sentence_entity()

        #扩展实体
        expand_terms = self.expand()

        #评价,这个还没有弄
        return self.evaluation(expand_terms)


    @abstractmethod
    def evaluation(self):
        pass
        
    #抽象方法, title扩展类, 用于扩展实体, 每个类必须定义该方法
    #也就是算法的精华部分, 最后会输出扩展的实体
    @abstractmethod
    def expand(self):
        pass

        
#这个是最一开始的思路
#问题中有A,B,C三个实体, 那么找到和A,B,C三个都有关联的实体,并且不过滤,然后去答案中找
#这个方法的缺点是,选择的实体过多, 没有说服力
#按照层过滤的方式
class level_filter_entity_expansioner(abstract_entity_expansioner):
    def __init__(self,mquestion,entity_finder,level1,level2,display):
        abstract_entity_expansioner.__init__(self,mquestion,entity_finder,display)
        self.level1 = level1
        self.level2 = level2

        #经过同义层过滤后的实体个数
        self.syn_filter_len = -1 

    def get_level(self):
        return self.level1,self.level2
        
    #评价实体扩充的好坏, 这个方法因为不唯一, 所以也有可能扩充到好几个方法
    #expand terms是一个set
    #另一个现有的数据是self.__sentence_entity, 因为可以直接访问到, 所以不会另建一个
    def evaluation(self,expand_terms):
        set1,set2 = expand_terms,self.get_sentence_total_entity()

        print("问题实体 :%s"%(self.title_entity()))
        print("扩展实体个数: %s"%(len(set1)))
        print("实体命中数目 : %s"%(bias_overlap_quantity(set1,set2)))
        print("实体命中率 : %s"%(bias_overlap_ratio(set1,set2)))
        print("答案实体总数目 : %s"%(len(set2)))
        print("句子数目 : %s"%(len(self.get_sentence_entity())))
        print("句子平均实体数 :%s"%(self.average_sentence_entity()))
        print("命中句子个数 :%s"%(self.hit_sentence(set1)))
        print("同义层过滤后实体个数 :%s"%(self.syn_filter_len))
        #print("实体重合样本 : %s "%(set1.intersection(set2)))

        return bias_overlap_ratio(set1,set2),bias_overlap_quantity(set1,set2),len(set1),self.syn_filter_len


    #命中句子个数
    def hit_sentence(self,expand_terms):
        result = 0
        for sentence,entities in self.get_sentence_entity():
            hit = 0
            for entity in entities:
                if entity in expand_terms:
                    hit += 1
            if hit >= 2:
                result += 1
        return result        
        
        
    #这个是扩展的通用方法, 给定输入的base_entity集合, 利用某种扩展规则进行扩展, 还有扩展层数
    #返回扩展的实体    
    def expand_with_entiy_type(self,base_entity,expand_rule,expand_level):

        #开始扩展
        #算法流程打算用基于栈的非递归方法
        
        #1. 记录当前的实体数量
        previous_entity_length = len(base_entity)
        #if self.display:
        #    print("句子实体 : %s"%(base_entity))

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
        result = self.expand_with_entiy_type(base_entity,expand_rule,self.level1)
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
        
        result = self.expand_with_entiy_type(entity,expand_rule,level2)
        
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
class SynRankRelateExpansioner(level_filter_entity_expansioner):

    #n是同义词过滤实体后的个数
    def __init__(self,mquestion,entity_finder,level1,level2,display,rank_alg,n=30):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)
        self.rank_alg = rank_alg
        self.n = n


    #=======================重写部分================================
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 10:
            return base_entity

        #建立图结构
        graph = self.build_graph(base_entity)

        #进行rank
        important_entity = self.rank_entity(graph)

        #rank
        important_entity = sorted(important_entity, key=important_entity.get, reverse=True)

        #先求最小索引
        l = min(len(important_entity),self.n)
        
        #得到top n, 并且并上基实体
        topn = set(important_entity[:l]).union(self.title_entity())

        return topn

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entiy_type(entity,expand_rule,level2)
        
        return result
        
    #重现
    def relate_filter(self,base_entity,entity):
        pass

    #==============================================================
        
    def build_graph(self,entity):
        gr = nx.Graph()
        gr.add_nodes_from(entity)
        node_pairs = list(itertools.combinations(entity,2))

        for ent1,ent2 in node_pairs:
            weight = get_weight2(ent1,ent2)
            if weight > 0:
                gr.add_edge(ent1,ent2,weight=weight)

        return gr

    def check_alg(self,alg):
        alg_set = ['hits','pagerank']
        if not alg in alg_set:
            print("not found alg")
            sys.exit(1)


    #用page rank 得到同义实体的重要成都
    def pagerank(self,gr):
        #去掉0初度的点, 防止pagerank报错
        W = nx.DiGraph(gr)    
        degree = W.out_degree(weight='weight')
        for(u,v,d) in W.edges(data=True):
            if degree[u] == 0:
                try:
                    gr.remove_node(u)
                except:
                    pass

        base_entity = self.title_entity()
        person = {}            
        for ent in gr.nodes():
            if ent in base_entity:
                person[ent] = 1
            else:
                person[ent] = 0.5

        pr = nx.pagerank_numpy(gr,weight='weight',alpha=0.8,personalization=person)#,max_iter=400)    

        return pr


    def hits(self,gr):
        h,a = nx.hits(gr,max_iter = 300)
        return h
        
    #得到过滤后的实体
    def rank_entity(self,gr):
        alg = self.rank_alg
        #检查算法的合理性
        self.check_alg(alg)

        if alg == 'pagerank':
            return self.pagerank(gr)
        elif alg == 'hits':
            return self.hits(gr)

        else:
            pass
        
        

#这个方法先扩同义词, 然后根据联通分量过滤或者度进行过滤
class SynDegreeRelateExpansioner(level_filter_entity_expansioner):
    
    def __init__(self,mquestion,entity_finder,level1,level2,display,alg):
        level_filter_entity_expansioner.__init__(self,mquestion,entity_finder,level1,level2,display)
        self.alg = alg

    #=======================重写部分================================
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 10:
            return base_entity

        #建立图结构
        graph = self.build_graph(base_entity)

        remove = self.remove_nodes(graph)

        important_entity = base_entity.difference(remove)
        
        important_entity = important_entity.union(self.title_entity())

        return important_entity

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entiy_type(entity,expand_rule,level2)
        
        return result
        
    #重现
    def relate_filter(self,base_entity,entity):
        pass

    #==============================================================
        
    def build_graph(self,entity):
        gr = nx.Graph()
        gr.add_nodes_from(entity)
        node_pairs = list(itertools.combinations(entity,2))

        for ent1,ent2 in node_pairs:
            weight = get_weight2(ent1,ent2)
            if weight > 0 :
                gr.add_edge(ent1,ent2,weight=weight)

        return gr

    #手工定规则, 约减节点
    #**************注意, 这是不要的节点**********************    
    def remove_nodes(self,gr):
        alg = self.alg 
        
        result = set()
        
        #联通度
        if alg == 'cc':

            #得到连通分量的子图
            sub_graphs = nx.connected_component_subgraphs(gr)

            #如果子图的节点数大于2, 那么则要这个子图
            for sub in sub_graphs:
                if len(sub) < 10:
                    result = result.union(sub.nodes())

                else:
                    pass

        elif alg == 'kcore':
            result = set(nx.k_crust(gr,k=2).nodes())

        else:
            print("error in alg")
            sys.exit(1)

        return result


#过滤关联层为主        
class RankRelateFilterExpansioner(SynRankRelateExpansioner):
    def __init__(self,mquestion,entity_finder,level1,level2,display,rank_alg,n=30):
        SynRankRelateExpansioner.__init__(self,mquestion,entity_finder,level1,level2,display,rank_alg,n=30)
    #*****************************************重写部分*********************************************
        
    #重写同义词过滤的方法
    def syn_filter(self,base_entity):

        #如果基实体数量小于十个, 那么直接返回
        if len(base_entity) < 10:
            return base_entity

        #建立图结构
        graph = self.build_graph(base_entity)

        #进行rank
        important_entity = self.rank_entity(graph)

        #=============================>改这儿
        print(important_entity)

        #rank
        important_entity = sorted(important_entity, key=important_entity.get, reverse=True)

        #先求最小索引
        l = min(len(important_entity),self.n)
        
        #得到top n, 并且并上基实体
        topn = set(important_entity[:l]).union(self.title_entity())

        return topn

    #重载relate_expand
    def relate_expand(self,entity):
        
        dumb,level2 = self.get_level()
        expand_rule = searcher.relate_entity
        
        result = self.expand_with_entiy_type(entity,expand_rule,level2)
        
        return result

    def relate_filter(self,base_entity,entity):
        pass

    #*********************************************************************************************        

    
