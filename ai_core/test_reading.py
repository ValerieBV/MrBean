from django.test import SimpleTestCase
from .reading import compare_reading, words, MAX_REFERENCE_WORDS, MAX_TRANSCRIPT_WORDS


class ReadingComparisonTests(SimpleTestCase):
    def test_case_punctuation_and_common_contractions_are_equivalent(self):
        result=compare_reading("I'm ready. We won't stop!", 'I am ready, we will not stop.')
        self.assertEqual(result['score'],10)
        self.assertEqual(result['difference_count'],0)
        self.assertEqual(words('ＣＡＴ ’hello’'), ['cat','hello'])

    def test_missing_substituted_and_extra_words_reduce_score(self):
        for transcript,field in [('I like books','missing_words'),('I really like cats','different_words'),('I really really like books','extra_words')]:
            result=compare_reading('I really like books',transcript)
            self.assertEqual(result['score'],7.5)
            self.assertEqual(result[field],1)

    def test_repeating_or_reordering_words_cannot_pass_as_full_reading(self):
        for text in ['one one one one','four three two one','one two three four one two three four']:
            self.assertLess(compare_reading('one two three four',text)['score'],10)
        self.assertEqual(compare_reading('one','one one one')['score'],0)

    def test_empty_and_excessive_text_is_not_a_grade(self):
        for reference,transcript in [('', 'hello'),('hello','!!!'),(None,'hello'),
                ('word '*(MAX_REFERENCE_WORDS+1),'word'),('word','word '*(MAX_TRANSCRIPT_WORDS+1))]:
            with self.assertRaises(ValueError):compare_reading(reference,transcript)

    def test_difference_display_is_bounded_but_score_uses_all_words(self):
        result=compare_reading('cat '*120,'dog '*120)
        self.assertEqual(result['score'],0)
        self.assertEqual(result['difference_count'],120)
        self.assertEqual(len(result['differences']),100)
