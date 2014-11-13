'''
这个文件的作用是封装conceptNet的一些功能,使得进行交互更为简单
'''

from .util import NLP
from conceptnet5.query import lookup
import sys

nlp = NLP()

#这个函数的作用是检测概念是否在conceptNet中,如果在则返回true, 如果不在返回false
def conceptnet_has_concept(concept):
    
    ans1 = lookup('/c/en/'+concept)

    indx = 0
    for item in ans1:
        indx += 1
        if indx > 0:
            break

    if indx > 0:
        return True

    return False

#试验品
class NaiveAccocSpaceWrapper(object):
    def __init__(self,path,finder):
        self.path = path
        self.finder = finder
        self.assoc = None

    def load(self):
        if self.assoc is not None:
            return

        try:
            from assoc_space import AssocSpace
            self.assoc = AssocSpace.load_dir(self.path)

        except:
            print("error in import assoc space")
            sys.exit(1)

    @staticmethod
    def passes_filter(label, filter):
        if filter is None:
            return True
        else:
            return field_match(label, filter)

    def expand_terms(self, terms, limit_per_term=10):
        """
        Given a list of weighted terms, add terms that are one step away in
        ConceptNet at a lower weight.

        This helps increase the recall power of the AssocSpace, because it
        means you can find terms that are too infrequent to have their own
        vector by looking up their neighbors. This forms a reasonable
        approximation of the vector an infrequent term would have anyway.
        """
        self.load()
        expanded = terms[:]
        for term, weight in terms:
            for edge in self.finder.lookup(term, limit=limit_per_term):
                if field_match(edge['start'], term):
                    neighbor = edge['end']
                elif field_match(edge['end'], term):
                    neighbor = edge['start']
                else:
                    continue
                neighbor_weight = weight * edge['weight'] * 0.1
                if edge['rel'].startswith('/r/Not'):
                    neighbor_weight *= -1
                expanded.append((neighbor, neighbor_weight))

        total_weight = sum(abs(weight) for (term, weight) in expanded)
        if total_weight == 0:
            return []
        return [(term, weight / total_weight) for (term, weight) in expanded]

    def associations(self, terms, filter=None, limit=20):
        self.load()
        vec = self.assoc.vector_from_terms(self.expand_terms(terms))
        similar = self.assoc.terms_similar_to_vector(vec)
        similar = [
            item for item in similar if item[1] > SMALL
            and self.passes_filter(item[0], filter)
        ][:limit]
        return similar

def init_assoc_space():
    assoc_space_dir = '/home/lavi/.conceptnet5/assoc/assoc-space-5.3'
    
    from conceptnet5.query import AssertionFinder as Finder
    finder = Finder()

    sa = NaiveAccocSpaceWrapper(assoc_space_dir,finder)

    return sa
    
