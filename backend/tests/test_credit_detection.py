import pytest
from app.credit_detection import describe_frame, detect, scrolling, sequence_confirmed, MAX_SAMPLES


def lines(texts, y=.2, spacing=.04):
    return [dict(text=text,confidence=.98,y0=y+i*spacing,y1=y+i*spacing+.025) for i,text in enumerate(texts)]


def card(texts):return describe_frame(lines(texts),dark=.95)


def test_dialogue_captions_and_black_frames_are_not_credits():
    assert not describe_frame(lines(['Written and directed by','someone you know'],y=.85),dark=.9)['positive']
    assert not describe_frame([],dark=1)['positive']
    assert not card(['THE END'])['positive']
    assert not card(['New York','Three years later'])['positive']


def test_credit_roles_over_scene_and_sparse_black_card():
    assert card(['Written and Directed by','Curry Barker'])['positive']
    assert describe_frame(lines(['Executive Producer','Jane Smith','Music by','John Jones']),dark=.1)['positive']
    assert not describe_frame([dict(text='Directed by',confidence=.2,y0=.2,y1=.3)],dark=.9)['positive']


def test_scroll_requires_multiple_matching_lines_and_consistent_upward_motion():
    a=describe_frame(lines(['Jane Smith','John Jones','Alice Walker','Oscar Green']),dark=.9)
    b=describe_frame(lines(['Jane Smith','John Jones','Alice Walker','Oscar Green'],y=.17),dark=.9)
    assert scrolling(a,b)
    assert not scrolling(a,a)
    assert not scrolling(b,a)
    assert not scrolling(a,describe_frame(lines(['Different Words','Other Text']),dark=.9))


def test_sequence_needs_distinct_roles_and_sustained_evidence():
    a=card(['Directed by','Jane Smith'])
    b=card(['Music by','John Jones'])
    c=card(['Produced by','Alice Walker'])
    assert not sequence_confirmed([a])
    assert not sequence_confirmed([a,a,a])
    assert sequence_confirmed([a,b,c])


def test_locates_first_credits_and_ignores_single_late_title():
    samples=[]
    def sample(t):
        samples.append(t)
        if 6600<=t<6620:return card(['Directed by','Jane Smith'])
        if 6620<=t<6640:return card(['Music by','John Jones'])
        if t>=6640:return card(['Produced by','Alice Walker'])
        if 6400<=t<6405:return card(['Directed by','Unrelated Person'])
        return card([])
    result=detect(7200,sample)
    assert 6600<=result['start']<=6602
    assert result['samples']<=MAX_SAMPLES
    assert result['evidence']['detector_version']==1


def test_mid_credit_black_fades_and_post_credit_scene_do_not_hide_earlier_run():
    def sample(t):
        if 6600<=t<6610:return card(['Directed by','Jane Smith'])
        if 6610<=t<6620:return card([])
        if 6620<=t<6640:return card(['Music by','John Jones'])
        if 6640<=t<6900:return card(['Produced by','Alice Walker'])
        return card([])  # Later post-credit scene cannot move marker later.
    assert detect(7200,sample)['start']==6600


def test_budget_and_unknown_ending_do_not_guess_duration():
    samples=[]
    result=detect(7200,lambda t:samples.append(t) or card([]))
    assert result['start'] is None and len(samples)<=MAX_SAMPLES
    assert detect(12,lambda t:pytest.fail('Short videos must not be sampled'))['start'] is None


def test_ocr_recognizes_real_rendered_cards_locally(tmp_path):
    pytest.importorskip('rapidocr');pytest.importorskip('onnxruntime')
    import numpy as np
    from PIL import Image,ImageDraw,ImageFont
    from app.credit_detection import Analyzer
    from pathlib import Path
    font=ImageFont.truetype(str(Path(__file__).resolve().parents[2]/'roku/fonts/DejaVuSans.ttf'),28)
    image=Image.new('RGB',(960,540),'black');draw=ImageDraw.Draw(image)
    draw.text((260,180),'Written and Directed by',font=font,fill='white')
    draw.text((345,240),'Jane Smith',font=font,fill='white')
    engine=Analyzer(tmp_path/'unused.mp4')
    engine.frame=lambda stamp:np.array(image)
    sample=engine.sample(0)
    assert sample['positive']
    assert any('jane' in text for text in sample['texts'])
