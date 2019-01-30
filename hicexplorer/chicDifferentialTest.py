import argparse
import sys
import numpy as np
import hicmatrix.HiCMatrix as hm
from hicexplorer import utilities

from hicexplorer._version import __version__
from .lib import Viewpoint

from scipy import stats

import os

import math
import logging
log = logging.getLogger(__name__)


def parse_arguments(args=None):
    parser = argparse.ArgumentParser(add_help=False,
                                     description='Test per line if two samples are differential expressed via chi2 contingency test.')

    parserRequired = parser.add_argument_group('Required arguments')

    parserRequired.add_argument('--interactionFile', '-if',
                                help='path to the interaction files which should be used for differential test.',
                                required=True,
                                nargs=2)

    parserRequired.add_argument('--alpha', '-a',
                                help='Accept all samples to significance level alpha',
                                type=float,
                                default=0.05,
                                required=True)
    parserRequired.add_argument('--outFileName', '-o',
                                help='File name to save the test results',
                                required=True)
    parserOpt = parser.add_argument_group('Optional arguments')

    parserOpt.add_argument('--statisticTest',
                           help='Type of test used for testing: fisher\'s exact test or chi2 contingency',
                           choices=['fisher', 'chi2'],
                           default='fisher')
    parserOpt.add_argument("--help", "-h", action="help", help="show this help message and exit")

    parserOpt.add_argument('--version', action='version',
                           version='%(prog)s {}'.format(__version__))
    return parser


def readInteractionFile(pInteractionFile):

    line_content = []
    data = []

    data_selector_viewpoint = 9
    data_selector_target = 12
    with open(pInteractionFile, 'r') as file:
        header = file.readline()
        for line in file.readlines():
            _line = line.strip().split('\t')
            if len(_line) <= 1:
                continue
            line_content.append(_line)
            data.append([float(_line[data_selector_viewpoint]), float(_line[data_selector_target])])

    return header, line_content, data


def chisquare_test(pDataFile1, pDataFile2, pAlpha):
    # pair of accepted/unaccepted and pvalue
    # True is rejection of H0
    # False acceptance of H0
    test_result = []
    # Find the critical value for alpha confidence level
    critical_value = stats.chi2.ppf(q=1 - pAlpha, df=1)
    zero_values_counter = 0
    for group1, group2 in zip(pDataFile1, pDataFile2):
        try:
            chi2, p_value, dof, ex = stats.chi2_contingency([group1, group2], correction=False)
            if chi2 >= critical_value:
                test_result.append((True, p_value))
            else:
                test_result.append((False, p_value))

        except ValueError:
            zero_values_counter += 1
            test_result.append((None, None))

    if zero_values_counter > 0:
        log.info('{} samples were not tested because at least one condition contained no data in both groups.'.format(zero_values_counter))
    return test_result


def fisher_exact_test(pDataFile1, pDataFile2, pAlpha):

    test_result = []
    for group1, group2 in zip(pDataFile1, pDataFile2):
        try:
            odds, p_value = stats.fisher_exact(np.ceil([group1, group2]))
            if p_value <= pAlpha:
                test_result.append((True, p_value))
            else:
                test_result.append((False, p_value))
        except ValueError:
            test_result.append((None, None))
    return test_result


def writeResult(pOutFileName, pData, pRejected, pHeaderOld, pHeaderNew, pViewpoint1, pViewpoint2, pAlpha, pTest):

    with open(pOutFileName, 'w') as file:
        header = '# Differential analysis result file of HiCExplorer\'s chicDifferentialTest version '
        header += str(__version__)
        header += '\n'

        if pRejected == True:
            header += '# This file contains the regions accepted as differential by {} test (H0 was rejected) \n'.format(pTest)
        elif pRejected == False:
            header += '# This file contains the regions rejected as differential by {} test (H0 was accepted) \n'.format(pTest)
        else:
            header += '# This file contains the regions which were not tested because of violation of {} test input conditions\n'.format(pTest)

        header += ' '.join(['# Used viewpoints regions: ', ' '.join(pViewpoint1), ' and ', ' '.join(pViewpoint2), '\n'])
        header += '#\n'

        header += '# Line 1 of a group contains data of viewpoint and target of sample 1, line 2 contains data of viewpoint and target of sample 2 \n'
        header += '# line 3 the p-value of the chi-squared contingency test.\n'
        header += '#\n'
        header += ' '.join(['# Alpha level', str(pAlpha)])
        header += '\n'
        header += ' '.join(['# Degrees of freedom', '1'])
        header += '\n'

        header += '\n'

        header += '\n\n'

        file.write(header)
        file.write(pHeaderOld)

        for data in pData:
            if data[2] is not None:
                file.write('\t'.join(data[0]) + '\n' + '\t'.join(data[1]) + '\n' + format(data[2], '.5f') + '\n')
            else:
                file.write('\t'.join(data[0]) + '\n' + '\t'.join(data[1]) + '\n')

            file.write('\n')


def main(args=None):
    args = parse_arguments().parse_args(args)

    header1, line_content1, data1 = readInteractionFile(args.interactionFile[0])
    header2, line_content2, data2 = readInteractionFile(args.interactionFile[1])

    if args.statisticTest == 'chi2':
        test_result = chisquare_test(data1, data2, args.alpha)
    elif args.statisticTest == 'fisher':
        test_result = fisher_exact_test(data1, data2, args.alpha)

    rejected_h0 = []

    non_rejected_h0 = []
    not_tested = []
    for i, result in enumerate(test_result):
        if result[0] == True:
            rejected_h0.append([line_content1[i], line_content2[i], result[1]])
        elif result[0] == False:
            non_rejected_h0.append([line_content1[i], line_content2[i], result[1]])
        elif result[0] is None:
            not_tested.append([line_content1[i], line_content2[i], None])

    header_new = args.interactionFile[0]
    header_new += ' '
    header_new += args.interactionFile[1]

    outFileName = args.outFileName.split('.')

    outRejectedH0 = outFileName[0] + '_rejected_H0.bed'
    outAcceptedH0 = outFileName[0] + '_accepted_H0.bed'
    outNoTest = outFileName[0] + '_no_test.bed'

    # log.debug('header1{}, \n\nheader2{}'.format(header1, header2))
    writeResult(outRejectedH0, rejected_h0, True, header1, header2, line_content1[0][:4], line_content2[0][:4], args.alpha, args.statisticTest)
    writeResult(outAcceptedH0, non_rejected_h0, False, header1, header2, line_content1[0][:4], line_content2[0][:4], args.alpha, args.statisticTest)
    writeResult(outNoTest, not_tested, None, header1, header2, line_content1[0][:4], line_content2[0][:4], args.alpha, args.statisticTest)
