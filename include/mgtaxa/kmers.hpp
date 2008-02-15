#ifndef KMERS_HPP_
#define KMERS_HPP_

#include <vector>
#include <iostream>
#include <exception>
#include <cmath>

namespace MGT {

//inline int ipow(int b, int p) {
//	return int(std::pow(b,p));
//}	

/** Small integer type to encode a nucledotide.*/
/** Example of encoding: 0,1,2,3,4 (0 - for N). */

typedef char INuc;

const int maxINuc = 5;

/** Type for one-letter encoded nucleotide.*/

typedef char CNuc;

const int maxCNuc = 256;

typedef unsigned long ULong;

const int maxKmerLen = 10;

/** Base exception class.*/

class KmerError: public std::exception
{
public:
	KmerError():
	m_msg("KmerError")
	{}
	KmerError(const char* msg):
	m_msg(msg)
	{}

  virtual const char* what() const throw()
  {
    return m_msg;
  }
 protected:
 const char* m_msg;
};

class KmerBadAlphabet: public KmerError
{
public:
	KmerBadAlphabet():
	KmerError("Alphabet is too long")
	{}
};

class KmerErrorLimits: public KmerError
{
public:
	KmerErrorLimits(const char* msg): KmerError(msg)
	{}
};

/** Exception raised when unallowed one-letter nucleotide code is received in the input. */  

class KmerBadNuc: public KmerError
{
  
  KmerBadNuc(CNuc cnuc) 
  {
  	m_msg[0] = cnuc;
  	m_msg[1] = '\0';
  }
  
  virtual const char* what() const throw()
  {
    return m_msg;
  }
  
  protected:
  
  char m_msg[2];
  
};	

/** Class that holds a counter for one k-mer along with jump pointers for next k-mers.*/

class KmerState {
	public:

	KmerState();

	typedef KmerState* PKmerState;

	public:

	/** Declared public only for access by KmerStates class.*/
	PKmerState m_next[maxINuc];

	/** Declared public only for access by KmerCounter class.*/
	ULong m_count;	
};

/** Pointer type for @see KmerCounter */

typedef KmerState::PKmerState PKmerState;

class Kmer {
	public:
	Kmer() {
		for(int i = 0; i < maxKmerLen; i++) { m_data[i] = 0; }
	}
	INuc m_data[maxKmerLen];
	inline INuc& operator[](int i) { return m_data[i]; }
	inline const INuc& operator[](int i) const { return m_data[i]; }	
};

class KmerStates {
	protected:
	typedef std::vector<KmerState> StateArray;
	typedef std::vector<Kmer> KmerArray; 
	public:
	//1. transition rule: nextItem(currItem,cNuc)->nextItem
	//2. itemToPointer(item) -> pointer
	//3. initAllItems()
	public:
		KmerStates(int kmerLen,int nAbc);
		PKmerState nextState(PKmerState pState,INuc c);
		PKmerState firstState();
	protected:
		PKmerState kmerState(const Kmer& kmer); 
		void nextKmer(const Kmer& currKmer, INuc c, Kmer& nextKmer);
		int kmerToIndex(const Kmer& kmer);
		void indexToKmer(int ind,Kmer& kmer);
		void initAllKmers();

	protected:
	/**number of "real" alphabet symbols.*/
	int m_nAbc;
	/**total number of encoded alphabet symbols - (m_nAbc + 1)*/
	int m_nCodes;
	int m_kmerLen;
	std::vector<int> m_blockSize;
	std::vector<int> m_blockStart;
	
	StateArray m_states;
	KmerArray m_kmers;
	
};


class KmerCounter {
	
	public:
	
	KmerCounter(int kmerLen);
	
	inline void doCNuc(CNuc cnuc) {
		doINuc(m_CNucToINuc[cnuc]);
	}
	
	inline void doINuc(INuc inuc) {
		m_pState = m_pStates->nextState(m_pState,inuc);
		m_pState->m_count++;
	}
	
	protected:
	
	void ctorCNucToINuc(const CNuc Abc[], int nAbc);
	
	protected:
	
	const CNuc * m_CNucToINuc;
	
	PKmerState m_pState;
	KmerStates *m_pStates;
	
	/**number of "real" alphabet symbols*/
	int m_nAbc;
	/**total number of encoded alphabet symbols (m_nAbc + 1)*/
	int m_nINuc;
	int m_kmerLen;
	
};


////////////////////////////////////////////////////////////////
///
/// Inline implementations
///
////////////////////////////////////////////////////////////////

inline KmerState::KmerState():
	m_count(0) {
		for(int i = 0; i < maxINuc; i++) {
			m_next[i] = 0;
		}
	}

inline PKmerState KmerStates::nextState(PKmerState pState,INuc c) {
	return pState->m_next[c];
}

inline PKmerState KmerStates::firstState() {
	return &m_states[0];
}


inline PKmerState KmerStates::kmerState(const Kmer& kmer) {
	int ind = kmerToIndex(kmer);
	return & m_states[ind]; 
}

inline int KmerStates::kmerToIndex(const Kmer& kmer) {
	int i = 0;
	for(; i < m_kmerLen; i++) {
		if( kmer[i] != 0 ) {
			break;
		}
	}
	int ndim = m_kmerLen - i;
	int blockStart = m_blockStart[ndim];
	int blockSize = m_blockSize[ndim];
	int extent = m_nAbc;
	int stride = 1;
	int ind = blockStart;
	for(; i < m_kmerLen; i++) {
		ind += kmer[i] * stride;
		stride *= extent;
	}
	return ind;
}


inline void KmerStates::indexToKmer(int ind, Kmer& kmer) {
	int iBlock = 0;
	for(; iBlock < m_kmerLen; iBlock++) {
		if( m_blockStart[iBlock] > ind ) {
			break;
		}
	}
	iBlock -= 1;
	int ndim = iBlock; // iBlock == number of non-0 dimensions
	int indBlock = ind - m_blockStart[ndim];
	int extent = m_nAbc;
	int stride = m_nAbc; 
	for( int i = m_kmerLen - ndim; i < m_kmerLen; i++ ) {
		kmer[i] = indBlock % stride;
		stride *= extent;
	}
}

} // namespace MGT

#endif /*KMERS_HPP_*/
