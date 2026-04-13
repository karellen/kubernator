# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2024 Karellen, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

# flake8: noqa

URLLIB_HEADERS_PATCH = ("@@ -2909,20 +2909,15 @@\n esp.\n-get\n headers\n-()\n %0A   \n",
                        "kubernetes/client/exceptions.py", "http_resp.headers", None, None, "urllib_headers_patch")
CUSTOM_OBJECT_PATCH_25 = ("""@@ -2532,32 +2532,1022 @@
 %0A        :param 
+str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A        :param 
 _preload_content
@@ -3587,32 +3587,32 @@
 nse object will%0A
-

@@ -6004,32 +6004,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -8031,32 +8031,64 @@
  'field_manager'
+,%0A            'field_validation'
 %0A        %5D%0A     
@@ -11267,32 +11267,255 @@
 ))  # noqa: E501
+%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501
 %0A%0A        header
@@ -14268,32 +14268,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -17722,32 +17722,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -19774,32 +19774,64 @@
  'field_manager'
+,%0A            'field_validation'
 %0A        %5D%0A     
@@ -23568,32 +23568,255 @@
 ))  # noqa: E501
+%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501
 %0A%0A        header
@@ -36926,32 +36926,160 @@
 pretty printed.%0A
+        :param str label_selector: A selector to restrict the list of returned objects by their labels. Defaults to everything.%0A
         :param i
@@ -40085,32 +40085,160 @@
 pretty printed.%0A
+        :param str label_selector: A selector to restrict the list of returned objects by their labels. Defaults to everything.%0A
         :param i
@@ -42457,32 +42457,62 @@
       'pretty',%0A
+            'label_selector',%0A
             'gra
@@ -45089,32 +45089,247 @@
 )  # noqa: E501%0A
+        if 'label_selector' in local_var_params and local_var_params%5B'label_selector'%5D is not None:  # noqa: E501%0A            query_params.append(('labelSelector', local_var_params%5B'label_selector'%5D))  # noqa: E501%0A
         if 'grac
@@ -48371,32 +48371,160 @@
 pretty printed.%0A
+        :param str label_selector: A selector to restrict the list of returned objects by their labels. Defaults to everything.%0A
         :param i
@@ -51650,32 +51650,160 @@
 pretty printed.%0A
+        :param str label_selector: A selector to restrict the list of returned objects by their labels. Defaults to everything.%0A
         :param i
@@ -54047,32 +54047,62 @@
       'pretty',%0A
+            'label_selector',%0A
             'gra
@@ -57245,32 +57245,247 @@
 )  # noqa: E501%0A
+        if 'label_selector' in local_var_params and local_var_params%5B'label_selector'%5D is not None:  # noqa: E501%0A            query_params.append(('labelSelector', local_var_params%5B'label_selector'%5D))  # noqa: E501%0A
         if 'grac
@@ -163053,32 +163053,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -166742,32 +166742,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -168967,32 +168967,64 @@
 field_manager',%0A
+            'field_validation',%0A
             'for
@@ -172538,32 +172538,255 @@
 )  # noqa: E501%0A
+        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501%0A
         if 'forc
@@ -173455,32 +173455,63 @@
   %5B'application/
+json-patch+json', 'application/
 merge-patch+json
@@ -175997,32 +175997,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -179690,32 +179690,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -181915,32 +181915,64 @@
 field_manager',%0A
+            'field_validation',%0A
             'for
@@ -185522,32 +185522,255 @@
 )  # noqa: E501%0A
+        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501%0A
         if 'forc
@@ -186498,32 +186498,63 @@
   %5B'application/
+json-patch+json', 'application/
 merge-patch+json
@@ -189050,32 +189050,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -192748,32 +192748,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -194973,32 +194973,64 @@
 field_manager',%0A
+            'field_validation',%0A
             'for
@@ -198586,32 +198586,255 @@
 )  # noqa: E501%0A
+        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501%0A
         if 'forc
@@ -199562,32 +199562,63 @@
   %5B'application/
+json-patch+json', 'application/
 merge-patch+json
@@ -202221,32 +202221,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -206032,32 +206032,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -208282,32 +208282,64 @@
 field_manager',%0A
+            'field_validation',%0A
             'for
@@ -212413,32 +212413,255 @@
 )  # noqa: E501%0A
+        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501%0A
         if 'forc
@@ -213330,32 +213330,63 @@
   %5B'application/
+json-patch+json', 'application/
 merge-patch+json
@@ -216001,32 +216001,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -219814,32 +219814,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -222064,32 +222064,64 @@
 field_manager',%0A
+            'field_validation',%0A
             'for
@@ -226237,32 +226237,255 @@
 )  # noqa: E501%0A
+        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501%0A
         if 'forc
@@ -227213,32 +227213,63 @@
   %5B'application/
+json-patch+json', 'application/
 merge-patch+json
@@ -227260,32 +227260,64 @@
 merge-patch+json
+', 'application/apply-patch+yaml
 '%5D)  # noqa: E50
@@ -229926,32 +229926,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -233744,32 +233744,1022 @@
 gicMergePatch).%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param b
@@ -235994,32 +235994,64 @@
 field_manager',%0A
+            'field_validation',%0A
             'for
@@ -240174,32 +240174,255 @@
 )  # noqa: E501%0A
+        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501%0A
         if 'forc
@@ -241150,32 +241150,63 @@
   %5B'application/
+json-patch+json', 'application/
 merge-patch+json
@@ -241197,32 +241197,64 @@
 merge-patch+json
+', 'application/apply-patch+yaml
 '%5D)  # noqa: E50
@@ -243613,32 +243613,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -246963,32 +246963,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -248988,32 +248988,64 @@
  'field_manager'
+,%0A            'field_validation'
 %0A        %5D%0A     
@@ -252551,32 +252551,255 @@
 ))  # noqa: E501
+%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501
 %0A%0A        header
@@ -255446,32 +255446,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -258787,32 +258787,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -260812,32 +260812,64 @@
  'field_manager'
+,%0A            'field_validation'
 %0A        %5D%0A     
@@ -264411,32 +264411,255 @@
 ))  # noqa: E501
+%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501
 %0A%0A        header
@@ -267375,32 +267375,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -270721,32 +270721,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -272746,32 +272746,64 @@
  'field_manager'
+,%0A            'field_validation'
 %0A        %5D%0A     
@@ -276351,32 +276351,255 @@
 ))  # noqa: E501
+%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501
 %0A%0A        header
@@ -279435,32 +279435,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -282907,32 +282907,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -284957,32 +284957,64 @@
  'field_manager'
+,%0A            'field_validation'
 %0A        %5D%0A     
@@ -289082,32 +289082,255 @@
 ))  # noqa: E501
+%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501
 %0A%0A        header
@@ -292106,32 +292106,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -295567,32 +295567,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -297617,32 +297617,64 @@
  'field_manager'
+,%0A            'field_validation'
 %0A        %5D%0A     
@@ -301784,32 +301784,255 @@
 ))  # noqa: E501
+%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation'%5D))  # noqa: E501
 %0A%0A        header
@@ -304877,32 +304877,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -308343,32 +308343,1022 @@
 icode/#IsPrint.%0A
+        :param str field_validation: fieldValidation instructs the server on how to handle objects in the request (POST/PUT/PATCH) containing unknown or duplicate fields. Valid values are: - Ignore: This will ignore any unknown fields that are silently dropped from the object, and will ignore all but the last duplicate field that the decoder encounters. This is the default behavior prior to v1.23. - Warn: This will send a warning via the standard warning response header for each unknown field that is dropped from the object, and for each duplicate field that is encountered. The request will still succeed if there are no other errors, and will only persist the last of any duplicate fields. This is the default in v1.23+ - Strict: This will fail the request with a BadRequest error if any unknown fields would be dropped from the object, or if any duplicate fields are present. The error returned from the server will contain all unknown and duplicate fields encountered. (optional)%0A
         :param _
@@ -310401,16 +310401,48 @@
 manager'
+,%0A            'field_validation'
 %0A       
@@ -314469,32 +314469,32 @@
 :  # noqa: E501%0A
-
             quer L
@@ -314549,32 +314549,255 @@
 s%5B'field_manager
+'%5D))  # noqa: E501%0A        if 'field_validation' in local_var_params and local_var_params%5B'field_validation'%5D is not None:  # noqa: E501%0A            query_params.append(('fieldValidation', local_var_params%5B'field_validation
 '%5D))  # noqa: E5
""", "kubernetes/client/api/custom_objects_api.py", "field_validation", 25, None, "field_validation_patch_25+")
