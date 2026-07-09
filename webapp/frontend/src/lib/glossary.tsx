import type { ReactNode } from 'react'
import GlossaryTerm from '../components/GlossaryTerm'

// 하드코딩된 임시 딕셔너리 — 몇 개 용어만 데모용으로 채워둠. 실제 서비스라면 백엔드/CMS로 옮길 것.
export const GLOSSARY: Record<string, string> = {
  ICCU: 'ICCU(통합충전제어장치) — 급속·완속 충전과 12V 보조배터리 충전을 함께 제어하는 전장 부품. 고장 시 저전압 방전이나 시동 불가로 이어질 수 있다.',
  ADAS: 'ADAS(첨단 운전자 보조 시스템) — 차선유지·자동긴급제동(AEB) 등 반자율주행 보조 기능의 총칭.',
  IEB: 'IEB(통합형 전자식 제동장치) — 유압 대신 전자 신호로 제동력을 제어하는 브레이크 시스템. 오작동 시 제동 지연이나 경고등 점등으로 나타날 수 있다.',
  OTA: 'OTA(무선 업데이트) — 서비스센터 방문 없이 무선으로 차량 소프트웨어를 업데이트하는 방식.',
  ECU: 'ECU(전자제어장치) — 엔진·변속기 등 차량 각 부위를 제어하는 컴퓨터 유닛.',
}

const TERM_PATTERN = new RegExp(`\\b(${Object.keys(GLOSSARY).join('|')})\\b`, 'g')

// 문자열에서 용어집 단어를 찾아 GlossaryTerm(점선 밑줄+호버 툴팁)으로 감싼다. 나머지는 그대로 둔다.
export function linkifyGlossary(text: string): ReactNode {
  const parts = text.split(TERM_PATTERN)
  return parts.map((part, i) =>
    GLOSSARY[part] ? (
      <GlossaryTerm key={i} term={part} description={GLOSSARY[part]}>
        {part}
      </GlossaryTerm>
    ) : (
      <span key={i}>{part}</span>
    ),
  )
}
