# Third-Party Notices

`altium-kicad-cli` is licensed under the MIT License (see [LICENSE](LICENSE)) and ships **zero bundled
third-party source code**. It has **no runtime dependencies** (Python standard library only).

This file records the **attribution chain** for projects that were used as **independent-design
references** — that is, for high-level *patterns* only. To be precise about provenance:

> **Independent reimplementation; no source copied; attribution retained where structures are
> referenced.** No source files, and no schema bytes, were copied from any project below. Our JSON
> Schema `$id`, titles, `ERROR` enum, and `protocol_version` field are original to this project.

## Provenance of the ported Altium parser logic

The OLE2/CFBF container-reading approach and the Altium record framing / `|KEY=VALUE|` field tokenizer
were **ported from the author's own prior work** (`schdoc_netlist.py` in the SoleStack repository) and
**relicensed by the same author** from a proprietary header to MIT for this project. The net-naming
defect in that prior code was deliberately **not** reused; the net layer was rebuilt. This is
first-party material and is covered by this repository's MIT LICENSE; it is listed here only for a
complete provenance record.

## Attribution chain — Altium MCP pattern reference

The optional Windows live-bridge design (`drivers/altium_live/`) and the structured `ERROR: CODE`
convention were informed, as an **independent-design reference for high-level patterns only**, by the
Altium MCP lineage:

- **flaco-source / altium-mcp** (2026) — file-based JSON request/response bridge between an external
  process and a running Altium instance; a `protocol_version` field on the bridge protocol; structured
  `ERROR: CODE` response strings. Referenced for *concept*, not code.
- **coffeenmusic** and **Siddharth Ahuja** (2025) — earlier Altium scripting / MCP work that the above
  builds upon, providing the DelphiScript-drives-Altium pattern.

Patterns referenced (no source copied): a file-based JSON bridge with atomic request/response files; a
protocol-version handshake; structured machine-readable error strings. Everything in this repository
implementing those patterns — the schema namespace, the error-code registry, the op-list vocabulary,
the bridge directory/locking scheme, and all code — is original to this project.

These upstream projects are distributed under the MIT License. The full MIT License text, reproduced for
each attributed copyright holder, follows.

---

### MIT License — flaco-source / altium-mcp (2026)

```
MIT License

Copyright (c) 2026 flaco-source (altium-mcp)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### MIT License — coffeenmusic / Siddharth Ahuja (2025)

```
MIT License

Copyright (c) 2025 coffeenmusic
Copyright (c) 2025 Siddharth Ahuja

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## MS10 — JLC/EasyEDA fetch + convert (subprocess / service; no source vendored)

`altium-kicad-cli` continues to ship **zero bundled third-party source code**. The MS10
"`jlc add`" feature uses the following projects **at arm's length** — as external binaries
run via subprocess, and as HTTP services queried over the network. No source files were
copied, imported, or linked from any of them.

### nlbn — Apache-2.0 (linkyourbin)

LCSC/EasyEDA → KiCad exporter. <https://github.com/linkyourbin/nlbn>. Invoked as the
`nlbn` subprocess by `akcli jlc add --to kicad`. If the optional auto-downloader ships or
caches the prebuilt `nlbn` binary, the Apache-2.0 LICENSE (and upstream NOTICE, if any) is
distributed alongside it.

### npnp — Apache-2.0 (linkyourbin)

LCSC/EasyEDA → Altium `.SchLib`/`.PcbLib` exporter.
<https://github.com/linkyourbin/npnp>. Invoked as the `npnp` subprocess by
`akcli jlc add --to altium`. Same Apache-2.0 redistribution terms as above.

> Because nlbn and npnp are licensed **Apache-2.0** (not AGPL), invoking them as
> subprocesses — and optionally redistributing their unmodified prebuilt binaries with
> attribution + the Apache-2.0 LICENSE/NOTICE — is permitted. This removes the
> copyleft/AGPL concern that previously discouraged automating an easyeda2kicad-style
> converter.

### jlcsearch (tscircuit) — MIT

Public search service over the JLCPCB/LCSC catalog, queried by `akcli jlc search`/`show`.
<https://github.com/tscircuit/jlcsearch>. (MIT text reproduced below.)

### jlcparts — MIT

Open dataset/tooling behind the catalog data. <https://github.com/yaqwsx/jlcparts>.
(MIT text reproduced below.)

### EasyEDA / LCSC / JLCPCB — data source (not a code dependency)

`akcli jlc show` performs a light, read-only metadata + 3D-availability lookup against
EasyEDA's **unofficial** Std-editor REST backend (`easyeda.com/api/products/...`,
`modules.easyeda.com/...`). These endpoints are undocumented and may change without notice;
they are the same backend the `easyeda2kicad.py` project (uPesy, GPL/community) documents.
We do not vendor easyeda2kicad and do not reuse its conversion code — conversion is
delegated to nlbn/npnp. EasyEDA, LCSC, and JLCPCB are trademarks of their respective owners;
this project is not affiliated with or endorsed by them.

---

### Apache License 2.0 — applies to nlbn and npnp (linkyourbin)

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   ---

   Copyright (c) linkyourbin — nlbn (https://github.com/linkyourbin/nlbn)
   Copyright (c) linkyourbin — npnp (https://github.com/linkyourbin/npnp)
   Licensed under the Apache License, Version 2.0.
   See http://www.apache.org/licenses/LICENSE-2.0
```

### MIT License — jlcsearch (tscircuit) and jlcparts

```
MIT License

Copyright (c) tscircuit — jlcsearch (https://github.com/tscircuit/jlcsearch)
Copyright (c) yaqwsx — jlcparts (https://github.com/yaqwsx/jlcparts)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

If you believe any attribution here is incomplete or incorrect, please open a GitHub issue so it can
be corrected.
